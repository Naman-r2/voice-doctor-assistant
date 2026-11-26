import { useEffect, useRef } from "react";
import * as THREE from "three";
import { voiceBus } from "../../lib/voiceBus.js";
import { dustFragment, dustVertex, sphereFragment, sphereVertex } from "./shaders.js";

const PARTICLES = 22_000;
const FEWEST = 3_000; // what a machine without a graphics card still gets
const SLOW_FRAME = 1 / 28; // seconds; slower than this for a while and the sphere thins out
const DUST = 1_400;
const CAMERA_Z = 6;
const FOV = 40;

// What each state looks like: two colours, how wound up the sphere is, how far apart.
const LOOKS = {
  idle: { a: "#dfe7ff", b: "#7aa2ff", twist: 0.0, scatter: 0.0, spin: 0.05 },
  ringing: { a: "#ffffff", b: "#9db8ff", twist: 0.6, scatter: 0.12, spin: 0.5 },
  listening: { a: "#eafff6", b: "#35e0a1", twist: 0.0, scatter: 0.0, spin: 0.07 },
  thinking: { a: "#fffbe0", b: "#f4e27a", twist: 2.4, scatter: 0.03, spin: 0.55 },
  speaking: { a: "#e6eeff", b: "#5b8cff", twist: 0.25, scatter: 0.0, spin: 0.12 },
  ended: { a: "#8b93a7", b: "#4a5165", twist: 0.0, scatter: 0.85, spin: 0.02 },
};

/** Points spread evenly over a unit sphere (a Fibonacci spiral), plus where each flies to when scattered. */
function sphereGeometry(count) {
  const position = new Float32Array(count * 3);
  const scatter = new Float32Array(count * 3);
  const seed = new Float32Array(count);
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = golden * i;
    position.set([Math.cos(theta) * r, y, Math.sin(theta) * r], i * 3);
    const far = 2.2 + Math.random() * 3.2;
    const u = Math.random() * Math.PI * 2;
    const v = Math.acos(2 * Math.random() - 1);
    scatter.set([far * Math.sin(v) * Math.cos(u), far * Math.cos(v), far * Math.sin(v) * Math.sin(u)], i * 3);
    seed[i] = Math.random();
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(position, 3));
  geometry.setAttribute("aScatter", new THREE.BufferAttribute(scatter, 3));
  geometry.setAttribute("aSeed", new THREE.BufferAttribute(seed, 1));
  return geometry;
}

function dustGeometry(count) {
  const position = new Float32Array(count * 3);
  const seed = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    position.set([(Math.random() - 0.5) * 26, (Math.random() - 0.5) * 16, -Math.random() * 16 + 2], i * 3);
    seed[i] = Math.random();
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(position, 3));
  geometry.setAttribute("aSeed", new THREE.BufferAttribute(seed, 1));
  return geometry;
}

/**
 * The scene behind the whole page: the agent as a sphere of particles in deep
 * space. It swells and spikes with the voice, winds up while thinking, flares
 * when something is booked, and drifts apart when the call ends. The camera
 * leans with the pointer.
 *
 * Everything it needs arrives through voiceBus, read once per frame.
 */
export default function Scene() {
  const mount = useRef(null);

  useEffect(() => {
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true, powerPreference: "high-performance" });
    } catch {
      return; // no WebGL: the page still works, just without the scene
    }
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(pixelRatio);
    renderer.setClearColor(0x000000, 0);
    mount.current.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 60);
    camera.position.z = CAMERA_Z;

    const uniforms = {
      uTime: { value: 0 },
      uEnergy: { value: 0 },
      uTwist: { value: 0 },
      uScatter: { value: 1 }, // starts blown apart and gathers: the opening shot
      uBurst: { value: 0 },
      uAlpha: { value: 0.9 },
      uScale: { value: 30 },
      uPixelRatio: { value: pixelRatio },
      uColorA: { value: new THREE.Color(LOOKS.idle.a) },
      uColorB: { value: new THREE.Color(LOOKS.idle.b) },
    };
    const sphere = new THREE.Points(
      sphereGeometry(PARTICLES),
      new THREE.ShaderMaterial({
        uniforms,
        vertexShader: sphereVertex,
        fragmentShader: sphereFragment,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    const rig = new THREE.Group(); // moved and scaled to sit behind its anchor on the page
    rig.add(sphere);
    scene.add(rig);

    const dustUniforms = { uTime: uniforms.uTime, uPixelRatio: uniforms.uPixelRatio };
    const dust = new THREE.Points(
      dustGeometry(DUST),
      new THREE.ShaderMaterial({
        uniforms: dustUniforms,
        vertexShader: dustVertex,
        fragmentShader: dustFragment,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    scene.add(dust);

    let width = 1;
    let height = 1;
    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();
    window.addEventListener("resize", resize);

    const pointer = { x: 0, y: 0 };
    const onPointer = (e) => {
      pointer.x = (e.clientX / width) * 2 - 1;
      pointer.y = (e.clientY / height) * 2 - 1;
    };
    window.addEventListener("pointermove", onPointer);

    // Where on the page the sphere belongs, in world units at the sphere's depth.
    const worldHeight = 2 * Math.tan((FOV * Math.PI) / 360) * CAMERA_Z;
    const place = () => {
      const box = voiceBus.anchor?.getBoundingClientRect();
      if (!box || !box.width) return { x: 0, y: 0, scale: 1.3 };
      const perPixel = worldHeight / height;
      return {
        x: (box.left + box.width / 2 - width / 2) * perPixel,
        y: -(box.top + box.height / 2 - height / 2) * perPixel,
        scale: (Math.min(box.width, box.height) * perPixel) / 2 / 1.25, // the sphere fills ~80% of its anchor
      };
    };

    // Keep the page responsive on weak graphics: draw fewer particles when frames run slow.
    let drawn = PARTICLES;
    let slowFor = 0;
    const adapt = (dt) => {
      slowFor = dt > SLOW_FRAME ? slowFor + dt : 0;
      if (slowFor > 0.6 && drawn > FEWEST) {
        drawn = Math.max(FEWEST, Math.floor(drawn * 0.6));
        sphere.geometry.setDrawRange(0, drawn);
        renderer.setPixelRatio(1);
        uniforms.uPixelRatio.value = 1;
        slowFor = 0;
      }
    };

    const clock = new THREE.Clock();
    const target = { a: new THREE.Color(), b: new THREE.Color() };
    let energy = 0;
    let spin = 0;
    let frame;

    const draw = () => {
      const elapsed = clock.getDelta();
      adapt(elapsed);
      const dt = Math.min(elapsed, 0.1);
      const look = LOOKS[voiceBus.state] || LOOKS.idle;
      const { bot, mic } = voiceBus.levels();
      const heard = voiceBus.state === "speaking" ? bot : voiceBus.state === "listening" ? mic : 0;
      const ease = 1 - Math.exp(-dt * 4);

      energy += (heard - energy) * (1 - Math.exp(-dt * 14));
      uniforms.uTime.value += dt * (still ? 0.2 : 1);
      uniforms.uEnergy.value = energy;
      uniforms.uTwist.value += (look.twist - uniforms.uTwist.value) * ease;
      uniforms.uScatter.value += (look.scatter - uniforms.uScatter.value) * (1 - Math.exp(-dt * 1.6));
      uniforms.uBurst.value = Math.max(0, 1 - (performance.now() - voiceBus.burstAt) / 1400);
      uniforms.uColorA.value.lerp(target.a.set(look.a), ease);
      uniforms.uColorB.value.lerp(target.b.set(look.b), ease);

      // sit behind the anchor, gliding there when the layout changes
      const spot = place();
      rig.position.x += (spot.x - rig.position.x) * ease;
      rig.position.y += (spot.y - rig.position.y) * ease;
      const scale = rig.scale.x + (spot.scale * (1 + energy * 0.12) - rig.scale.x) * ease;
      rig.scale.setScalar(scale);
      uniforms.uScale.value = 22 * scale;

      spin += dt * (still ? 0 : look.spin + energy * 0.5);
      sphere.rotation.y = spin;
      sphere.rotation.x = Math.sin(spin * 0.3) * 0.25;

      // the camera leans with the pointer; near things move more than far ones
      rig.rotation.y += (pointer.x * 0.35 - rig.rotation.y) * ease * 0.6;
      rig.rotation.x += (pointer.y * 0.22 - rig.rotation.x) * ease * 0.6;
      dust.position.x += (-pointer.x * 0.5 - dust.position.x) * ease * 0.4;
      dust.position.y += (pointer.y * 0.3 - dust.position.y) * ease * 0.4;

      renderer.render(scene, camera);
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onPointer);
      sphere.geometry.dispose();
      sphere.material.dispose();
      dust.geometry.dispose();
      dust.material.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return <div className="scene" ref={mount} aria-hidden="true" />;
}
