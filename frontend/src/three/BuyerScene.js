import React, { useMemo, useRef, Suspense, Component } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float, Line, Sparkles } from "@react-three/drei";
import * as THREE from "three";

function BuyerCore({ active }) {
  const ref = useRef();
  useFrame((state, delta) => {
    if (ref.current) {
      ref.current.rotation.y += delta * 0.25;
      ref.current.rotation.x += delta * 0.08;
    }
  });
  return (
    <group>
      <mesh ref={ref}>
        <icosahedronGeometry args={[1.2, 2]} />
        <meshStandardMaterial
          color={active ? "#00E5FF" : "#0aa9c2"}
          emissive="#00E5FF"
          emissiveIntensity={active ? 0.9 : 0.5}
          roughness={0.2}
          metalness={0.7}
          flatShading
        />
      </mesh>
      <mesh>
        <icosahedronGeometry args={[1.55, 1]} />
        <meshBasicMaterial color="#00E5FF" wireframe transparent opacity={0.18} />
      </mesh>
      <mesh scale={1.9}>
        <sphereGeometry args={[1, 24, 24]} />
        <meshBasicMaterial
          color="#00E5FF"
          transparent
          opacity={0.06}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <mesh scale={2.6}>
        <sphereGeometry args={[1, 24, 24]} />
        <meshBasicMaterial
          color="#0077ff"
          transparent
          opacity={0.04}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <pointLight color="#00E5FF" intensity={6} distance={12} />
    </group>
  );
}

function OrbitRing({ count, radius, color, speed, size = 0.06, tiltAxis = "x", tilt = 0 }) {
  const group = useRef();
  const nodes = useMemo(() => {
    return new Array(count).fill(0).map((_, i) => {
      const a = (i / count) * Math.PI * 2 + Math.random() * 0.3;
      const r = radius + (Math.random() - 0.5) * 0.35;
      return [Math.cos(a) * r, (Math.random() - 0.5) * 0.6, Math.sin(a) * r];
    });
  }, [count, radius]);

  useFrame((_, delta) => {
    if (group.current) group.current.rotation.y += delta * speed;
  });

  return (
    <group ref={group} rotation={tiltAxis === "x" ? [tilt, 0, 0] : [0, 0, tilt]}>
      {nodes.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[size, 12, 12]} />
          <meshStandardMaterial
            color={color}
            emissive={color}
            emissiveIntensity={1.4}
            roughness={0.3}
          />
        </mesh>
      ))}
      {nodes.slice(0, Math.min(count, 10)).map((p, i) => (
        <Line
          key={`l-${i}`}
          points={[[0, 0, 0], p]}
          color={color}
          lineWidth={0.6}
          transparent
          opacity={0.12}
        />
      ))}
    </group>
  );
}

function SceneContent({ stage, active }) {
  const candidates = stage?.candidates ?? 40;
  const shortlisted = stage?.shortlisted ?? 18;
  const verified = stage?.verified ?? 9;
  const negotiating = stage?.negotiating ?? 4;

  return (
    <>
      <ambientLight intensity={0.6} />
      <pointLight position={[6, 6, 6]} intensity={2.2} color="#ffffff" />
      <pointLight position={[-6, -4, -6]} intensity={1.4} color="#00FF66" />
      <pointLight position={[0, 3, 4]} intensity={1.6} color="#00E5FF" />
      <spotLight position={[0, 8, 2]} intensity={1.2} angle={0.6} color="#ffffff" />

      <Float speed={1.4} rotationIntensity={0.35} floatIntensity={0.6}>
        <BuyerCore active={active} />
      </Float>

      <OrbitRing count={Math.min(candidates, 46)} radius={3.4} color="#3a4a66" speed={0.12} size={0.045} tilt={0.35} />
      <OrbitRing count={Math.min(shortlisted, 22)} radius={2.7} color="#00E5FF" speed={0.2} size={0.06} tilt={-0.2} tiltAxis="z" />
      <OrbitRing count={Math.min(verified, 12)} radius={2.05} color="#00FF66" speed={0.3} size={0.075} tilt={0.15} />
      <OrbitRing count={Math.min(negotiating, 6)} radius={1.55} color="#FF3366" speed={0.45} size={0.09} tilt={-0.3} tiltAxis="z" />

      <Sparkles count={60} scale={9} size={1.5} speed={0.3} color="#00E5FF" opacity={0.4} />
    </>
  );
}

function FallbackVisual() {
  return (
    <div className="w-full h-full flex items-center justify-center">
      <div className="relative">
        <div className="w-48 h-48 rounded-full bg-primary/20 blur-2xl animate-pulseGlow" />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-28 h-28 rounded-full border border-primary/40 bg-primary/10 glow-primary" />
        </div>
      </div>
    </div>
  );
}

class CanvasBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {}
  render() {
    if (this.state.failed) return <FallbackVisual />;
    return this.props.children;
  }
}

export default function BuyerScene({ stage, active = true, className = "" }) {
  return (
    <div className={className}>
      <CanvasBoundary>
        <Canvas
          dpr={[1, 1.8]}
          camera={{ position: [0, 0.5, 6.5], fov: 45 }}
          gl={{ antialias: true, alpha: false, preserveDrawingBuffer: true, powerPreference: "high-performance" }}
          onCreated={({ gl }) => {
            gl.setClearColor(0x05050a, 1);
          }}
        >
          <Suspense fallback={null}>
            <SceneContent stage={stage} active={active} />
          </Suspense>
        </Canvas>
      </CanvasBoundary>
    </div>
  );
}
