"""Contract tests using fake Docker and HTTP. Never touches real containers."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
PWSH = os.environ.get("CHAOS_TEST_PWSH") or shutil.which("pwsh")
FAKE_DOCKER = r'''
import json,os,sys
from pathlib import Path
root=Path(os.environ["CHAOS_TEST_ROOT"])
args=sys.argv[1:]
if args[:1]==["--host"]: args=args[2:]
with (root/"calls.jsonl").open("a",encoding="utf-8") as f: f.write(json.dumps(args)+"\n")
state=json.loads((root/"state.json").read_text(encoding="utf-8"))
if args[:2]==["context","show"]: print("local")
elif args[:2]==["context","inspect"]: print(state.get("endpoint","npipe:////./pipe/dockerDesktopLinuxEngine"))
elif args[:1]==["compose"]: print("fake-container")
elif args[:1]==["inspect"]:
 labels={"com.docker.compose.project":"src","com.docker.compose.service":state["service"],
         "com.docker.compose.project.config_files":str(root/"src"/"docker-compose.yml")}
 if state.get("foreign"): labels["com.docker.compose.project.config_files"]=str(root/"other.yml")
 print(json.dumps([{"Config":{"Labels":labels},"State":{"Running":True,"Paused":state["paused"]}}]))
elif args[:1] in [["pause"],["unpause"]]:
 state["paused"]=args[0]=="pause"
 (root/"state.json").write_text(json.dumps(state),encoding="utf-8")
 if args[0]=="pause" and state.get("pause_failure"): sys.exit(1)
else: sys.exit(2)
'''
BOOTSTRAP = r'''
param([string]$Scenario,[string]$LeasePath)
$ErrorActionPreference='Stop'
$root=$env:CHAOS_TEST_ROOT
$script:calls=0
function Invoke-WebRequest {
 param([string]$Uri,[int]$TimeoutSec,[switch]$UseBasicParsing)
 $script:calls++
 $state=Get-Content (Join-Path $root 'state.json') -Raw | ConvertFrom-Json
 if($Scenario -eq 'stop-baseline' -and $script:calls -eq 3){Set-Content (Join-Path $root 'chaos-scripts/STOP') 'STOP'}
 if($Scenario -eq 'stop-fault' -and $state.paused){Set-Content (Join-Path $root 'chaos-scripts/STOP') 'STOP'}
 $module=($Uri -split '/')[-1]
 if($Scenario -eq 'bad-baseline' -or ($state.paused -and ($module -eq 'CustomerManagement' -or $Scenario -eq 'threshold'))){
  return @{StatusCode=200;Content='module is offline'}
 }
 return @{StatusCode=200;Content=($module -replace 'Management',' Management')}
}
$runner=Join-Path $root 'chaos-scripts/PauseExperiment.ps1'
if($Scenario -eq 'worker'){ & $runner -Watchdog -LeasePath $LeasePath; exit 0 }
if($Scenario -eq 'death'){
 $pwsh=(Get-Process -Id $PID).Path
 $parent=Start-Process $pwsh -ArgumentList @('-NoProfile','-NonInteractive','-Command','Start-Sleep -Seconds 60') -WindowStyle Hidden -PassThru
 $directory=Join-Path $root 'chaos-scripts/results/death'; New-Item -ItemType Directory $directory -Force | Out-Null
 $lease=Join-Path $directory 'lease.json'
 @{Service='customermanagementapi';ContainerId='fake-container';Endpoint='npipe:////./pipe/dockerDesktopLinuxEngine'
 DurationSeconds=5;ParentId=$parent.Id;ParentStartedUtc=$parent.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content $lease
 $bootstrap=$PSCommandPath.Replace("'","''"); $leaseArg=$lease.Replace("'","''")
 $cmd="& '$bootstrap' -Scenario worker -LeasePath '$leaseArg'"
 $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
 $guardian=Start-Process $pwsh -ArgumentList @('-NoProfile','-NonInteractive','-EncodedCommand',$encoded) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'worker-out.log') -RedirectStandardError (Join-Path $root 'worker-error.log') -PassThru
 try {
  $timer=[Diagnostics.Stopwatch]::StartNew()
  while(-not(Test-Path (Join-Path $directory 'watchdog-ready'))){
   if($guardian.HasExited -or $timer.Elapsed.TotalSeconds -gt 15){throw ('Watchdog readiness failed: ' + (Get-Content (Join-Path $root 'worker-error.log') -Raw -ErrorAction SilentlyContinue))}
   Start-Sleep -Milliseconds 100
  }
  # Watchdog owns the same OS lock used by all scripts.
  $handle=$null
  try {$handle=[IO.File]::Open((Join-Path $root 'chaos-scripts/experiment.lock'),'OpenOrCreate','ReadWrite','None')}
  catch [IO.IOException] {}
  if($handle){$handle.Dispose();throw 'Watchdog did not hold experiment.lock'}
  Set-Content (Join-Path $directory 'armed') 'armed'
  $state=Get-Content (Join-Path $root 'state.json') -Raw | ConvertFrom-Json
  $state.paused=$true; $state | ConvertTo-Json | Set-Content (Join-Path $root 'state.json')
  Stop-Process -Id $parent.Id
  if(-not $guardian.WaitForExit(20000)){throw ('Watchdog failed to recover after parent death: ' + (Get-Content (Join-Path $root 'worker-error.log') -Raw -ErrorAction SilentlyContinue))}
  if($guardian.ExitCode -ne 0){throw 'Watchdog failed'}
  if(-not(Test-Path (Join-Path $directory 'watchdog-report.json'))){throw 'Watchdog evidence missing'}
 } finally {
  if(-not $parent.HasExited){Stop-Process -Id $parent.Id}
  if(-not $guardian.HasExited){Stop-Process -Id $guardian.Id}
 }
 exit 0
}
$lock=$null
try {
 if($Scenario -eq 'lock'){$lock=[IO.File]::Open((Join-Path $root 'chaos-scripts/experiment.lock'),'OpenOrCreate','ReadWrite','None')}
 if($Scenario -eq 'dry'){& (Join-Path $root 'chaos-scripts/pause-vehicle-api.ps1')}
 else{& (Join-Path $root 'chaos-scripts/pause-customer-api.ps1') -Execute -DurationSeconds 5 -BaselineRounds 1 -RecoveryTimeoutSeconds 10}
} finally {if($lock){$lock.Dispose()}}
'''

@unittest.skipUnless(PWSH, "Set CHAOS_TEST_PWSH or put PowerShell 7 on PATH")
class PauseContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pause-contract-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        scripts = self.root / "chaos-scripts"
        scripts.mkdir()
        (self.root / "src").mkdir()
        (self.root / "src/docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
        for name in ["ChaosSafety.psm1", "PauseExperiment.ps1", "pause-customer-api.ps1", "pause-vehicle-api.ps1", "analyze.ps1"]:
            shutil.copyfile(SOURCE / name, scripts / name)
        self.state = {"service": "customermanagementapi", "paused": False}
        self.save_state()
        (self.root / "docker.py").write_text(FAKE_DOCKER, encoding="utf-8")
        (self.root / "docker.cmd").write_text(f'@"{sys.executable}" "{self.root / "docker.py"}" %*\n', encoding="utf-8")
        (self.root / "bootstrap.ps1").write_text(BOOTSTRAP, encoding="utf-8")
        self.env = dict(os.environ, CHAOS_TEST_ROOT=str(self.root))
        self.env["PATH"] = str(self.root) + os.pathsep + self.env["PATH"]
        for key in ["DOCKER_HOST", "DOCKER_TLS_VERIFY", "DOCKER_CONTEXT"]:
            self.env.pop(key, None)

    def save_state(self):
        (self.root / "state.json").write_text(json.dumps(self.state), encoding="utf-8")

    def run_scenario(self, scenario):
        return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(self.root / "bootstrap.ps1"),
                               "-Scenario", scenario], env=self.env, capture_output=True, text=True, timeout=90)

    def calls(self):
        path = self.root / "calls.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def assert_no_fault(self, scenario):
        result = self.run_scenario(scenario)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any(call[0] in ["pause", "unpause"] for call in self.calls()))

    def test_dry_run_changes_nothing_even_with_stop(self):
        self.state["service"] = "vehiclemanagementapi"
        self.save_state()
        (self.root / "chaos-scripts/STOP").touch()
        result = self.run_scenario("dry")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DRY RUN", result.stdout)
        self.assertFalse(any(call[0] in ["pause", "unpause"] for call in self.calls()))

    def test_stop_after_baseline_prevents_injection(self):
        self.assert_no_fault("stop-baseline")

    def test_bad_baseline_prevents_injection(self):
        self.assert_no_fault("bad-baseline")

    def test_foreign_checkout_refused(self):
        self.state["foreign"] = True
        self.save_state()
        self.assert_no_fault("normal")

    def test_remote_endpoint_refused_before_container_lookup(self):
        self.state["endpoint"] = "tcp://remote:2375"
        self.save_state()
        self.assert_no_fault("normal")
        self.assertFalse(any(call[0] == "compose" for call in self.calls()))

    def test_cross_process_lock_refuses_overlap(self):
        self.assert_no_fault("lock")

    def test_normal_completion_restores_and_records_recovery(self):
        result = self.run_scenario("normal")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reports = list((self.root / "chaos-scripts/results").glob("*/report.json"))
        self.assertEqual(len(reports), 1)
        report = json.loads(reports[0].read_text(encoding="utf-8-sig"))
        self.assertTrue(report["Restored"])
        self.assertTrue(report["Recovered"])
        self.assertEqual({s["Phase"] for s in report["Samples"]}, {"baseline", "fault", "recovery"})
        self.assertTrue(reports[0].with_name("samples.csv").exists())
        self.assertFalse(json.loads((self.root / "state.json").read_text())["paused"])

    def test_unaffected_threshold_aborts_and_rolls_back(self):
        result = self.run_scenario("threshold")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(next((self.root / "chaos-scripts/results").glob("*/report.json")).read_text(encoding="utf-8-sig"))
        self.assertIn("Safety threshold breached", report["RollbackReason"])
        self.assertTrue(report["Recovered"])

    def test_detached_watchdog_restores_after_parent_death_and_holds_lock(self):
        result = self.run_scenario("death")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(["unpause", "fake-container"], self.calls())
        self.assertFalse(json.loads((self.root / "state.json").read_text())["paused"])


    def test_stop_during_fault_restores(self):
        result = self.run_scenario("stop-fault")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(next((self.root / "chaos-scripts/results").glob("*/report.json")).read_text(encoding="utf-8-sig"))
        self.assertEqual(report["RollbackReason"], "Manual kill switch")
        self.assertTrue(report["Restored"])
        self.assertTrue(report["Recovered"])

    def test_failed_pause_command_still_rolls_back(self):
        self.state["pause_failure"] = True
        self.save_state()
        result = self.run_scenario("normal")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(["unpause", "fake-container"], self.calls())
        self.assertFalse(json.loads((self.root / "state.json").read_text())["paused"])

    def test_scorer_excludes_both_target_pages_from_containment(self):
        for service, target in [("customermanagementapi", "CustomerManagement"), ("vehiclemanagementapi", "VehicleManagement")]:
            report = {"RunId": service, "Experiment": "pause-api", "TargetService": service,
                      "Restored": True, "Recovered": True, "RecoverySeconds": 1,
                      "RollbackReason": "Maximum fault duration reached",
                      "Samples": [{"Phase": "fault", "Module": module, "Healthy": module != target,
                                   "StatusCode": None if module == target else 200}
                                  for module in ["CustomerManagement", "VehicleManagement", "WorkshopManagement"]]}
            path = self.root / "synthetic-report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            output = self.root / ("analysis-" + service)
            result = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File",
                                     str(self.root / "chaos-scripts/analyze.ps1"), "-ReportPath", str(path),
                                     "-OutputDirectory", str(output)], env=self.env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            analysis = json.loads((output / "analysis.json").read_text(encoding="utf-8-sig"))
            dimensions = {d["Name"]: d for d in analysis["Analyses"][0]["Dimensions"]}
            self.assertEqual(dimensions["Blast radius containment"]["Earned"], 25)
            self.assertTrue(dimensions["Graceful degradation"]["Measured"])
            self.assertFalse(dimensions["Data integrity"]["Measured"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
