"""Inspect Compose and bounded source files, never export configuration values."""
import json
import re
from pathlib import Path
import yaml
from agent.schemas import Dependency, Evidence, Service

EXCLUDED = {"bin", "obj", "node_modules", "wwwroot", ".git"}


def source_files(directory: Path):
    for file in sorted(directory.rglob("*")):
        if file.is_file() and not EXCLUDED.intersection(file.parts) and file.suffix in {".cs", ".csproj", ".json"} and file.stat().st_size < 512_000:
            yield file


def discover(root: Path):
    compose_path = root / "src/docker-compose.yml"
    raw = yaml.safe_load(compose_path.read_text(encoding="utf-8-sig"))
    entries = raw.get("services", {})
    services, dependencies, warnings = [], [], []
    compose_lines = compose_path.read_text(encoding="utf-8-sig").splitlines()
    for name, config in entries.items():
        build = config.get("build", {})
        if isinstance(build, str):
            build = {"context": build}
        folder = (compose_path.parent / build.get("context", ".") / Path(build.get("dockerfile", "Dockerfile")).parent).resolve()
        # Do not follow arbitrary Compose paths outside the checkout.
        has_code = "dockerfile" in build and folder.is_relative_to(root.resolve())
        files = list(source_files(folder)) if has_code else []
        # Follow bounded local ProjectReferences, not arbitrary package/cache trees.
        seen = set(files)
        frontier = [f for f in files if f.suffix == ".csproj"]
        for _ in range(3):
            next_frontier = []
            for project in frontier:
                project_text = project.read_text(encoding="utf-8-sig", errors="replace")
                for reference in re.findall(r'<ProjectReference\s+Include="([^"]+)"', project_text):
                    referenced = (project.parent / reference.replace("\\", "/")).resolve()
                    if not referenced.is_relative_to((root / "src").resolve()) or not referenced.is_file() or referenced in seen:
                        continue
                    extra = [f for f in source_files(referenced.parent) if f not in seen]
                    seen.update(extra)
                    files.extend(extra)
                    next_frontier.append(referenced)
            frontier = next_frontier
        dockerfile = folder / Path(build.get("dockerfile", "Dockerfile")).name
        docker_text = dockerfile.read_text(encoding="utf-8-sig", errors="replace") if has_code and dockerfile.exists() and dockerfile.stat().st_size < 512_000 else ""
        text = "\n".join(f.read_text(encoding="utf-8-sig", errors="replace") for f in files if f.suffix == ".cs")
        env = config.get("environment", {})
        env_names = list(env) if isinstance(env, dict) else [v.split("=", 1)[0] for v in env]
        env_names = sorted(set(env_names + re.findall(r"(?m)^\s*ENV\s+([A-Za-z_][A-Za-z_0-9]*)", docker_text)))
        health_match = re.search(r'(?:UseHealthChecks|MapHealthChecks)\("([^"\r\n]+)"', text)
        controls = [label for pattern, label in [(r"WaitAndRetry", "delayed retry found; inspect bound and duration"), (r"RetryAsync", "retry found; inspect policy"), (r"CircuitBreaker", "circuit breaker found"), (r"\.Timeout\s*=", "explicit HTTP timeout found"), (r"using\s*\(?", "using/disposal syntax found (not proof of complete cleanup)")] if re.search(pattern, text)]
        limits = config.get("deploy", {}).get("resources", {}).get("limits", {}).copy()
        for key in ("mem_limit", "cpus"):
            if key in config:
                limits[key] = config[key]
        service = Service(name=name, role="application" if has_code else "infrastructure", runtime=".NET" if has_code else config.get("image", "unknown").split(":")[0], ports=[str(p) if not isinstance(p, dict) else f"{p.get('published', '')}:{p.get('target', '')}" for p in config.get("ports", [])], networks=list(config.get("networks", ["default"])), replicas=config.get("deploy", {}).get("replicas", 1), limits=limits, restart=config.get("restart", "not configured"), healthcheck=bool(config.get("healthcheck")) or health_match is not None, health_path=health_match.group(1) if health_match else None, environment_names=env_names, code_paths=[str(f.relative_to(root)).replace("\\", "/") for f in files], controls=controls, routes=sorted(set(re.findall(r'\[(?:Route|HttpGet|HttpPost|HttpPut|HttpDelete)\("([^"\r\n]*)"', text))))
        services.append(service)
        frameworks = set()
        for project in files:
            if project.suffix == ".csproj":
                frameworks.update(re.findall(r"<TargetFramework>([A-Za-z0-9.]+)</TargetFramework>", project.read_text(encoding="utf-8-sig", errors="replace")))
        if frameworks:
            service.runtime = ".NET " + ", ".join(sorted(frameworks))
        service.framework = "ASP.NET Core" if re.search(r"Add(?:Mvc|Controllers)|WebApplication.CreateBuilder", text) else ".NET worker" if has_code else "infrastructure image"
        if docker_text:
            service.dockerfile = dockerfile.relative_to(root).as_posix()
            service.code_paths.append(service.dockerfile)
            service.build_images = re.findall(r"(?im)^\s*FROM\s+([a-zA-Z0-9_./:@-]+)", docker_text)
        line = next((i for i, v in enumerate(compose_lines, 1) if re.match(rf"  {re.escape(name)}:\s*$", v)), 1)
        for target in config.get("depends_on", []):
            if target in entries:
                dependencies.append(Dependency(source=name, target=target, kind="startup", confidence="high", evidence=Evidence(path="src/docker-compose.yml", line=line, description="Compose depends_on"), detail="Startup ordering only; runtime availability is not established by this edge."))
            else:
                warnings.append(f"{name}: unresolved startup target {target}")
        for file in files:
            if not file.name.startswith("appsettings") or file.suffix != ".json":
                continue
            try:
                settings = json.loads(file.read_text(encoding="utf-8-sig"))
            except ValueError:
                warnings.append(f"Invalid settings JSON: {file.relative_to(root)}")
                continue
            # Production config is the deployed setting in this Compose file.
            if file.name != "appsettings.Production.json":
                continue
            def walk(value, keys=()):
                if isinstance(value, dict):
                    for k, v in value.items():
                        yield from walk(v, (*keys, k))
                elif isinstance(value, list):
                    for v in value:
                        yield from walk(v, keys)
                elif isinstance(value, str):
                    yield keys, value
            lines = file.read_text(encoding="utf-8-sig").splitlines()
            for keys, value in walk(settings):
                joined = ".".join(keys).lower()
                if any(k in joined for k in ("password", "secret", "apikey", "token", "username")):
                    continue
                for target in entries:
                    if target == name or not re.search(rf"(?<![\w-]){re.escape(target)}(?![\w-])", value, re.I):
                        continue
                    kind = "database" if "connectionstring" in joined else "broker" if "rabbit" in joined else "logging" if "serilog" in joined else "mail" if "smtp" in joined else "http" if "apiservicelocations" in joined else None
                    if kind:
                        loc = next((i for i, row in enumerate(lines, 1) if f'"{keys[-1]}"' in row), 1)
                        dependencies.append(Dependency(source=name, target=target, kind=kind, confidence="high", evidence=Evidence(path=file.relative_to(root).as_posix(), line=loc, description=f"Production configuration key {'.'.join(keys)} references known service (value withheld)"), detail="Configured runtime dependency; actual failure impact requires verification."))
    overlay = root / "chaos-scripts/dependency-overlay.json"
    if overlay.exists() and "rabbitmq" in entries:
        topology = json.loads(overlay.read_text(encoding="utf-8-sig"))
        for direction in ("publishes", "subscribes"):
            for name, events in topology.get(direction, {}).items():
                if name in entries:
                    dependencies.append(Dependency(source=name, target="rabbitmq", kind="broker", confidence="medium", evidence=Evidence(path=overlay.relative_to(root).as_posix(), line=1, description=f"Curated {direction}: {', '.join(events)}; corroborate with handler source"), detail=f"Asynchronous {direction}; disconnection may delay processing rather than make all endpoints unavailable."))
    return services, dependencies, warnings
