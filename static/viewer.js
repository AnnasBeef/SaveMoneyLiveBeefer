import * as THREE from "https://esm.sh/three@0.160.0";
import { GLTFLoader } from "https://esm.sh/three@0.160.0/examples/jsm/loaders/GLTFLoader.js";

const canvas = document.getElementById("steak-canvas");
const modelUrl = canvas?.dataset?.modelUrl || "/static/models/uploads_files_5709017_Steak+model.glb";

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.45;

const scene = new THREE.Scene();
scene.background = null;

const camera = new THREE.PerspectiveCamera(38, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(0, 0.22, 1.72);

scene.add(new THREE.AmbientLight(0xffffff, 1.15));

const keyLight = new THREE.DirectionalLight(0xffffff, 1.05);
keyLight.position.set(4, 4, 3);
scene.add(keyLight);

const fillLight = new THREE.DirectionalLight(0xfff7e6, 1.0);
fillLight.position.set(-4, 2, 2);
scene.add(fillLight);

const rimLight = new THREE.DirectionalLight(0xcde7ff, 0.85);
rimLight.position.set(0, 2, -4);
scene.add(rimLight);

let steakModel = null;
const loader = new GLTFLoader();
loader.load(
  modelUrl,
  (gltf) => {
    steakModel = gltf.scene;

    const box = new THREE.Box3().setFromObject(steakModel);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    const targetSize = 3.45;
    const scale = targetSize / maxDim;

    steakModel.scale.setScalar(scale);
    steakModel.position.sub(center.multiplyScalar(scale));

    scene.add(steakModel);
  },
  undefined,
  (err) => {
    console.error("Failed to load GLB model:", err);
  }
);

let rotationSpeed = 0;
let targetSpeed = 0;
let lastScrollY = window.scrollY;
let lastScrollAt = performance.now();

function onScroll() {
  const currentY = window.scrollY;
  const delta = currentY - lastScrollY;
  lastScrollY = currentY;

  if (delta === 0) return;

  // Scroll down => clockwise. Scroll up => counterclockwise.
  const direction = delta > 0 ? -1 : 1;
  const magnitude = Math.min(Math.abs(delta) * 0.0025, 0.09);
  targetSpeed = direction * magnitude;
  lastScrollAt = performance.now();
}

window.addEventListener("scroll", onScroll, { passive: true });

function resize() {
  const w = window.innerWidth;
  const h = window.innerHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}

window.addEventListener("resize", resize);

let previousTime = performance.now();
function animate(now) {
  requestAnimationFrame(animate);

  const dt = Math.max((now - previousTime) / 1000, 0);
  previousTime = now;

  if (now - lastScrollAt > 120) {
    targetSpeed = 0;
  }

  const blend = 1 - Math.exp(-10 * dt);
  rotationSpeed += (targetSpeed - rotationSpeed) * blend;

  if (steakModel) {
    steakModel.rotation.y += rotationSpeed;
  }

  camera.lookAt(0, 0, 0);
  renderer.render(scene, camera);
}

requestAnimationFrame(animate);
