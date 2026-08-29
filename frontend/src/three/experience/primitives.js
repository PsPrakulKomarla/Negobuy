import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Edges, RoundedBox } from "@react-three/drei";
import * as THREE from "three";
import { SCENES, clamp } from "./helpers";

/* ---- The NegoBuy AI: an angular command monolith (NOT a sphere / brain) ---- */
export function Monolith() {
  const seam = useRef();
  const halo = useRef();
  useFrame((s) => {
    const t = s.clock.elapsedTime;
    if (seam.current) seam.current.material.opacity = 0.5 + 0.4 * (0.5 + 0.5 * Math.sin(t * 1.6));
    if (halo.current) halo.current.rotation.y = t * 0.25;
  });
  const dark = { color: "#070b16", metalness: 0.85, roughness: 0.28 };
  return (
    <group position={[0, 0, 0]}>
      {/* hex pedestal */}
      <mesh position={[0, 0.18, 0]}>
        <cylinderGeometry args={[1.7, 2.05, 0.36, 6]} />
        <meshStandardMaterial color="#0a0f1c" metalness={0.9} roughness={0.35} />
        <Edges threshold={15} color="#123a63" />
      </mesh>
      {/* rotating base ring of small nodes */}
      <group ref={halo} position={[0, 0.42, 0]}>
        {new Array(18).fill(0).map((_, i) => {
          const a = (i / 18) * Math.PI * 2;
          return (
            <mesh key={i} position={[Math.cos(a) * 2.35, 0, Math.sin(a) * 2.35]}>
              <boxGeometry args={[0.06, 0.06, 0.06]} />
              <meshStandardMaterial color="#00E5FF" emissive="#00E5FF" emissiveIntensity={1.4} />
            </mesh>
          );
        })}
      </group>
      {/* central slab */}
      <mesh position={[0, 2.0, 0]}>
        <boxGeometry args={[0.95, 3.4, 0.55]} />
        <meshStandardMaterial {...dark} emissive="#00E5FF" emissiveIntensity={0.18} />
        <Edges threshold={15} color="#00E5FF" />
      </mesh>
      {/* emissive seam */}
      <mesh ref={seam} position={[0, 2.0, 0.29]}>
        <planeGeometry args={[0.16, 2.9]} />
        <meshBasicMaterial color="#7ff4ff" transparent opacity={0.7} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      {/* side blades */}
      <mesh position={[0.92, 1.45, 0]} rotation={[0, 0, 0.06]}>
        <boxGeometry args={[0.34, 2.3, 0.42]} />
        <meshStandardMaterial {...dark} emissive="#00E5FF" emissiveIntensity={0.1} />
        <Edges threshold={15} color="#0e7fa8" />
      </mesh>
      <mesh position={[-0.92, 1.45, 0]} rotation={[0, 0, -0.06]}>
        <boxGeometry args={[0.34, 2.3, 0.42]} />
        <meshStandardMaterial {...dark} emissive="#00E5FF" emissiveIntensity={0.1} />
        <Edges threshold={15} color="#0e7fa8" />
      </mesh>
      <pointLight position={[0, 2.6, 0.7]} color="#00E5FF" intensity={4.5} distance={10} />
    </group>
  );
}

/* ---- A supplier: angular kiosk / pillar with a colored faceplate ---- */
export function Kiosk({ position = [0, 0, 0], color = "#2f7bff", scale = 1, dim = false }) {
  const c = dim ? "#243244" : color;
  return (
    <group position={position} scale={scale}>
      <mesh position={[0, 0.1, 0]}>
        <cylinderGeometry args={[0.62, 0.78, 0.2, 6]} />
        <meshStandardMaterial color="#0a0f1c" metalness={0.85} roughness={0.4} />
        <Edges threshold={15} color="#16324f" />
      </mesh>
      <mesh position={[0, 0.95, 0]}>
        <boxGeometry args={[0.7, 1.5, 0.4]} />
        <meshStandardMaterial color="#080d18" metalness={0.7} roughness={0.3} emissive={c} emissiveIntensity={dim ? 0.05 : 0.22} />
        <Edges threshold={15} color={c} />
      </mesh>
      <mesh position={[0, 1.05, 0.22]}>
        <planeGeometry args={[0.44, 0.9]} />
        <meshBasicMaterial color={c} transparent opacity={dim ? 0.12 : 0.55} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
    </group>
  );
}

/* ---- Beam connecting two points with a traveling data packet ---- */
export function Beam({ from, to, color = "#00E5FF", speed = 0.6 }) {
  const packet = useRef();
  const { mid, len, quat, a, dir } = useMemo(() => {
    const av = new THREE.Vector3(...from);
    const bv = new THREE.Vector3(...to);
    const d = bv.clone().sub(av);
    const l = d.length();
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.clone().normalize());
    return { mid: av.clone().add(bv).multiplyScalar(0.5), len: l, quat: q, a: av, dir: d };
  }, [from, to]);
  useFrame((s) => {
    if (packet.current) {
      const t = (s.clock.elapsedTime * speed) % 1;
      packet.current.position.copy(a).addScaledVector(dir, t);
    }
  });
  return (
    <group>
      <mesh position={mid} quaternion={quat}>
        <cylinderGeometry args={[0.016, 0.016, len, 6]} />
        <meshBasicMaterial color={color} transparent opacity={0.4} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh ref={packet}>
        <sphereGeometry args={[0.06, 8, 8]} />
        <meshBasicMaterial color={color} transparent opacity={0.95} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
    </group>
  );
}

/* ---- Floating angular info shard (mission requirement) ---- */
export function Shard({ position, rotation = [0, 0, 0], color = "#00E5FF" }) {
  const ref = useRef();
  const seed = useMemo(() => Math.random() * 6.28, []);
  useFrame((s) => {
    if (ref.current) ref.current.position.y = position[1] + Math.sin(s.clock.elapsedTime * 0.8 + seed) * 0.08;
  });
  return (
    <group ref={ref} position={position} rotation={rotation}>
      <RoundedBox args={[1.15, 0.62, 0.05]} radius={0.06} smoothness={3}>
        <meshStandardMaterial color="#081020" metalness={0.6} roughness={0.2} emissive={color} emissiveIntensity={0.14} transparent opacity={0.92} />
      </RoundedBox>
      <mesh position={[0, 0, 0.03]}>
        <planeGeometry args={[1.15, 0.62]} />
        <meshBasicMaterial color={color} transparent opacity={0.06} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
    </group>
  );
}

/* ---- Instanced supplier market that filters down with scroll (discovery) ---- */
export function MarketField({ scroll }) {
  const mesh = useRef();
  const N = 340;
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const data = useMemo(
    () =>
      new Array(N).fill(0).map(() => ({
        x: (Math.random() - 0.5) * 42,
        z: -2 - Math.random() * 27,
        y: 0.15 + Math.random() * 1.7,
        q: Math.random(),
        ph: Math.random() * 6.28,
      })),
    []
  );
  useFrame((s) => {
    if (!mesh.current) return;
    const sp = clamp(scroll.get(), 0, 1) * (SCENES - 1);
    const local = clamp((sp - 1.5) / 1.25, 0, 1); // filtering progress across discovery scene
    const thr = local * 0.985;
    for (let i = 0; i < N; i++) {
      const d = data[i];
      const survive = clamp((d.q - thr) / 0.05, 0, 1);
      const pulse = 0.12 + 0.04 * Math.sin(s.clock.elapsedTime * 2 + d.ph);
      dummy.position.set(d.x, d.y + Math.sin(s.clock.elapsedTime * 0.6 + d.ph) * 0.06, d.z);
      dummy.scale.setScalar(survive * pulse);
      dummy.updateMatrix();
      mesh.current.setMatrixAt(i, dummy.matrix);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
  });
  return (
    <instancedMesh ref={mesh} args={[null, null, N]}>
      <octahedronGeometry args={[1, 0]} />
      <meshStandardMaterial color="#0bd3ff" emissive="#00E5FF" emissiveIntensity={1.7} transparent opacity={0.92} />
    </instancedMesh>
  );
}

/* ---- Landed-cost tower: components assemble upward with scroll ---- */
export function CostTower({ scroll, position = [5, 0, 1] }) {
  const g = useRef();
  const segs = [
    { h: 1.4, color: "#00E5FF" },
    { h: 0.55, color: "#00FF66" },
    { h: 0.3, color: "#37a2ff" },
    { h: 0.22, color: "#ffb020" }, // assumption
  ];
  const refs = [useRef(), useRef(), useRef(), useRef()];
  useFrame(() => {
    const sp = clamp(scroll.get(), 0, 1) * (SCENES - 1);
    const local = clamp((sp - 6.45) / 0.9, 0, 1);
    segs.forEach((_, i) => {
      const start = i / segs.length;
      const a = clamp((local - start) * segs.length, 0, 1);
      if (refs[i].current) refs[i].current.scale.y = Math.max(0.001, a);
    });
  });
  let base = 0.2;
  return (
    <group ref={g} position={position}>
      {segs.map((seg, i) => {
        const y = base + seg.h / 2;
        base += seg.h;
        return (
          <mesh key={i} ref={refs[i]} position={[0, y, 0]}>
            <boxGeometry args={[0.9, seg.h, 0.9]} />
            <meshStandardMaterial
              color="#0a1120"
              metalness={0.6}
              roughness={0.3}
              emissive={seg.color}
              emissiveIntensity={0.3}
            />
            <Edges threshold={15} color={seg.color} />
          </mesh>
        );
      })}
    </group>
  );
}

/* ---- Completion seal ring around the core ---- */
export function SealRing({ scroll }) {
  const ref = useRef();
  useFrame((s) => {
    if (!ref.current) return;
    const sp = clamp(scroll.get(), 0, 1) * (SCENES - 1);
    const local = clamp((sp - 9.5) / 1, 0, 1);
    ref.current.rotation.z = s.clock.elapsedTime * 0.4;
    ref.current.scale.setScalar(0.6 + local * 0.8);
    ref.current.material.opacity = local * 0.85;
  });
  return (
    <mesh ref={ref} position={[0, 1.9, 0]} rotation={[Math.PI / 2, 0, 0]}>
      <torusGeometry args={[2.6, 0.05, 8, 80]} />
      <meshBasicMaterial color="#00FF66" transparent opacity={0} blending={THREE.AdditiveBlending} depthWrite={false} />
    </mesh>
  );
}
