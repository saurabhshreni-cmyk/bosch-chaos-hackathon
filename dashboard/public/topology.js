import * as THREE from 'three';
import { OrbitControls } from '/vendor/OrbitControls.js';

const layout = {
  webapp: [0, -7, 'Web app', '#007f79'],
  customermanagementapi: [-5, -3, 'Customer API', '#3976b6'],
  vehiclemanagementapi: [0, -3, 'Vehicle API', '#3976b6'],
  workshopmanagementapi: [5, -3, 'Workshop API', '#3976b6'],
  sqlserver: [-3, 1, 'SQL Server', '#82599b'],
  rabbitmq: [3, 1, 'RabbitMQ', '#bf851c'],
  workshopmanagementeventhandler: [-7, 5, 'Workshop handler', '#6b8188'],
  notificationservice: [-2.4, 5, 'Notifications', '#6b8188'],
  invoiceservice: [2.4, 5, 'Invoices', '#6b8188'],
  auditlogservice: [7, 5, 'Audit log', '#6b8188'],
  mailserver: [-6, 9, 'MailDev', '#6b8188'],
  logserver: [0, 9, 'Seq logs', '#6b8188'],
  timeservice: [6, 9, 'Time service', '#6b8188'],
};
const routeColors = { HTTP: '#219c92', SQL: '#a7b3bb', SMTP: '#cf7c96' };

function labelTexture(text) {
  const canvas = document.createElement('canvas'); canvas.width = 256; canvas.height = 64;
  const context = canvas.getContext('2d');
  context.font = '600 24px Segoe UI, Arial'; context.textAlign = 'center'; context.textBaseline = 'middle';
  context.strokeStyle = '#191c20'; context.lineWidth = 5; context.strokeText(text, 128, 32, 244);
  context.fillStyle = '#e5ebef'; context.fillText(text, 128, 32, 244);
  const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export function mountTopology(canvas, onSelect) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor('#191c20'); renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight('#ffffff', '#738b97', 2.6));
  const sunlight = new THREE.DirectionalLight('#ffffff', 3); sunlight.position.set(5, 18, 9); scene.add(sunlight);
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 200);
  const controls = new OrbitControls(camera, canvas);
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  controls.target.set(0, 0, 1); controls.enableDamping = true;
  controls.minDistance = 14; controls.maxDistance = 65; controls.maxPolarAngle = Math.PI / 2.3;
  controls.enablePan = false; controls.autoRotate = !reducedMotion; controls.autoRotateSpeed = 0.35;
  const grid = new THREE.GridHelper(24, 24, '#645535', '#30353a'); grid.position.set(0, -0.03, 1); scene.add(grid);
  const nodes = new Map(), pickables = [], raycaster = new THREE.Raycaster();
  let selected = 'workshopmanagementapi', currentState, routeKey = '', routes = new THREE.Group();
  scene.add(routes);
  for (const [id, [x, z, title, color]] of Object.entries(layout)) {
    const group = new THREE.Group(); group.position.set(x, 0, z); scene.add(group);
    const geometry = id === 'sqlserver' ? new THREE.CylinderGeometry(0.7, 0.7, 1.6, 32) : new THREE.BoxGeometry(1.4, 1.6, 1.1);
    const material = new THREE.MeshStandardMaterial({ color, roughness: 0.45, metalness: 0.1 });
    const body = new THREE.Mesh(geometry, material); body.position.y = 0.85; body.userData.id = id; group.add(body); pickables.push(body);
    const outline = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), new THREE.LineBasicMaterial({ color: '#334b55', transparent: true, opacity: 0.3 }));
    outline.position.copy(body.position); group.add(outline);
    const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 8), new THREE.MeshBasicMaterial({ color: '#9ba9af' })); lamp.position.set(0.4, 1.15, 0.6); group.add(lamp);
    const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: labelTexture(title), depthTest: false }));
    label.position.y = 3; label.scale.set(3.1, 0.58, 1); label.userData.id = id; group.add(label); pickables.push(label);
    const selection = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1.7, 1.9, 1.4)), new THREE.LineBasicMaterial({ color: '#e2be69' }));
    selection.position.y = 0.85; group.add(selection);
    nodes.set(id, { group, body, lamp, label, selection, baseColor: color, title, healthy: null });
  }

  function fit() {
    const { width, height } = canvas.getBoundingClientRect();
    renderer.setSize(width, height, false); camera.aspect = width / Math.max(1, height); camera.updateProjectionMatrix();
  }
  function reset() {
    fit();
    const distance = canvas.clientWidth < 500 ? 44 : 29;
    camera.position.set(distance * 0.38, distance * 0.76, distance * 0.65);
    controls.target.set(0, 0, 1); controls.update();
  }
  reset(); const resize = new ResizeObserver(fit); resize.observe(canvas);

  function select(id) {
    if (!nodes.has(id)) return;
    selected = id;
    canvas.dataset.selectedService = id;
    for (const [name, node] of nodes) node.selection.visible = name === selected;
    const row = currentState?.health?.containers?.find(row => row.service === id);
    const links = (currentState?.dependencies?.edges || []).filter(edge => edge.from === id || edge.to === id);
    const module = { customermanagementapi: 'CustomerManagement', vehiclemanagementapi: 'VehicleManagement', workshopmanagementapi: 'WorkshopManagement' }[id];
    const page = currentState?.health?.modules?.find(row => row.name === module);
    onSelect({ id, title: nodes.get(id).title, state: row?.state || 'Unknown', health: row?.health || 'No health check', healthy: nodes.get(id).healthy, probe: page ? page.healthy ? 'Page responding' : page.failureMode || 'Failed page probe' : 'No page probe', links });
  }
  let pointerStart;
  const down = event => { pointerStart = [event.clientX, event.clientY]; controls.autoRotate = false; };
  const up = event => {
    if (!pointerStart || Math.hypot(event.clientX - pointerStart[0], event.clientY - pointerStart[1]) > 6) return;
    const rect = canvas.getBoundingClientRect();
    raycaster.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), camera);
    const hit = raycaster.intersectObjects(pickables.filter(item => item.visible))[0]; if (hit) select(hit.object.userData.id);
  };
  canvas.addEventListener('pointerdown', down); canvas.addEventListener('pointerup', up);
  const keydown = event => {
    if (!['ArrowLeft', 'ArrowRight', '+', '-', 'Home'].includes(event.key)) return;
    event.preventDefault(); controls.autoRotate = false;
    if (event.key === 'Home') reset();
    else if (['+', '-'].includes(event.key)) zoom(event.key === '+' ? 0.88 : 1.12);
    else { const offset = camera.position.clone().sub(controls.target); offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), event.key === 'ArrowLeft' ? -0.15 : 0.15); camera.position.copy(controls.target).add(offset); }
  };
  canvas.addEventListener('keydown', keydown);
  function zoom(factor) { const offset = camera.position.clone().sub(controls.target); offset.setLength(THREE.MathUtils.clamp(offset.length() * factor, controls.minDistance, controls.maxDistance)); camera.position.copy(controls.target).add(offset); controls.update(); }
  function disposeObjects(object) { object.traverse(child => { child.geometry?.dispose(); const materials = Array.isArray(child.material) ? child.material : child.material ? [child.material] : []; for (const material of materials) { material.map?.dispose(); material.dispose(); } }); }
  function update(state) {
    currentState = state;
    for (const [id, node] of nodes) {
      const row = state.health.containers.find(row => row.service === id);
      const module = { customermanagementapi: 'CustomerManagement', vehiclemanagementapi: 'VehicleManagement', workshopmanagementapi: 'WorkshopManagement' }[id];
      const page = state.health.modules.find(row => row.name === module);
      node.healthy = !row || state.health.dockerError ? null : row.state === 'running' && row.health !== 'unhealthy' && page?.healthy !== false;
      node.body.material.color.set(node.healthy === false ? '#cf2858' : node.baseColor);
      node.lamp.material.color.set(node.healthy === null ? '#9ba9af' : node.healthy ? '#198457' : '#cf2858');
    }
    const edges = state.dependencies?.edges || [], key = JSON.stringify(edges);
    if (key !== routeKey) {
      disposeObjects(routes); scene.remove(routes); routes = new THREE.Group(); scene.add(routes); routeKey = key;
      for (const edge of edges) {
        const from = nodes.get(edge.from), to = nodes.get(edge.to); if (!from || !to) continue;
        const start = from.group.position.clone().add(new THREE.Vector3(0, 0.2, 0));
        const end = to.group.position.clone().add(new THREE.Vector3(0, 0.2, 0));
        const middle = start.clone().lerp(end, 0.5); middle.y = 0.65;
        const curve = new THREE.QuadraticBezierCurve3(start, middle, end);
        routes.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(30)), new THREE.LineBasicMaterial({ color: routeColors[edge.type] || '#83acd2', transparent: true, opacity: 0.75 })));
        const tangent = curve.getTangent(0.85).normalize();
        const arrow = new THREE.Mesh(new THREE.ConeGeometry(0.1, 0.3, 8), new THREE.MeshBasicMaterial({ color: routeColors[edge.type] || '#83acd2' }));
        arrow.position.copy(curve.getPoint(0.85)); arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tangent); routes.add(arrow);
      }
    }
    select(selected);
  }
  renderer.setAnimationLoop(time => {
    for (const node of nodes.values()) node.body.material.emissive.set(node.healthy === false ? '#cf2858' : '#000000');
    for (const node of nodes.values()) node.body.material.emissiveIntensity = node.healthy === false ? 0.1 + (reducedMotion ? 0 : Math.sin(time / 500) * 0.08) : 0;
    controls.update();
    // Screen-sized labels are culled when they would overlap or leave the viewport.
    const occupied = [], width = canvas.clientWidth, height = canvas.clientHeight;
    for (const node of nodes.values()) node.label.position.y = width < 500 ? 4.5 : 3;
    scene.updateMatrixWorld(); camera.updateMatrixWorld();
    const ordered = [...nodes.entries()].sort(([a], [b]) => a === selected ? -1 : b === selected ? 1 : 0);
    const bodyRects = [...nodes.values()].map(node => {
      const world = node.body.getWorldPosition(new THREE.Vector3()), distance = camera.position.distanceTo(world);
      const unit = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * distance / Math.max(1, height);
      const point = world.project(camera), x = (point.x + 1) * width / 2, y = (1 - point.y) * height / 2;
      return { left: x - 1.1 / unit, right: x + 1.1 / unit, top: y - 1.3 / unit, bottom: y + 1.3 / unit };
    });
    const overlaps = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
    let framedNodes = 0;
    for (const [id, node] of ordered) {
      const center = node.body.getWorldPosition(new THREE.Vector3()).project(camera);
      if (Math.abs(center.x) < 0.95 && Math.abs(center.y) < 0.95 && center.z < 1) framedNodes++;
      const world = node.label.getWorldPosition(new THREE.Vector3());
      const distance = camera.position.distanceTo(world);
      const unit = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * distance / Math.max(1, height);
      node.label.scale.set(100 * unit, 25 * unit, 1);
      const projected = world.project(camera), x = (projected.x + 1) * width / 2, y = (1 - projected.y) * height / 2;
      const rect = { left: x - 54, right: x + 54, top: y - 16, bottom: y + 16 };
      node.label.visible = width >= 500 && projected.z < 1 && rect.left >= 0 && rect.right <= width && rect.top >= 0 && rect.bottom <= height && !occupied.some(other => overlaps(rect, other)) && !bodyRects.some(other => overlaps(rect, other));
      if (node.label.visible) occupied.push(rect);
    }
    canvas.dataset.framedNodes = String(framedNodes); canvas.dataset.nodeCount = String(nodes.size);
    renderer.render(scene, camera);
  });
  return { update, select, reset, zoom, rotating: () => controls.autoRotate, toggleRotation: () => { controls.autoRotate = !controls.autoRotate; return controls.autoRotate; },
    dispose() { resize.disconnect(); canvas.removeEventListener('pointerdown', down); canvas.removeEventListener('pointerup', up); canvas.removeEventListener('keydown', keydown); renderer.setAnimationLoop(null); controls.dispose(); disposeObjects(scene); renderer.dispose(); renderer.forceContextLoss(); } };
}
