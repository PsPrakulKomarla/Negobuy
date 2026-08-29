import React, { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Grid, Sparkles, Float } from "@react-three/drei";
import { SCENES, clamp, band } from "./helpers";
import {
  Monolith,
  Kiosk,
  Beam,
  Shard,
  MarketField,
  CostTower,
  SealRing,
} from "./primitives";

/* Fades/scales an entire scene subtree in and out around its scene index. */
function Scene({ scroll, index, half = 0.62, fade = 0.42, rise = 0.5, children }) {
  const ref = useRef();
  const init = useRef(false);
  useFrame(() => {
    const g = ref.current;
    if (!g) return;
    const sp = clamp(scroll.get(), 0, 1) * (SCENES - 1);
    const p = band(sp, index - half, index + half, fade);
    if (!init.current) {
      g.traverse((o) => {
        if (o.material) {
          o.userData.o0 = o.material.opacity != null ? o.material.opacity : 1;
          o.material.transparent = true;
        }
      });
      init.current = true;
    }
    g.visible = p > 0.004;
    if (g.visible) {
      g.traverse((o) => {
        if (o.material) o.material.opacity = (o.userData.o0 != null ? o.userData.o0 : 1) * p;
      });
      g.position.y = (1 - p) * rise;
      g.scale.setScalar(0.9 + 0.1 * p);
    }
  });
  return <group ref={ref}>{children}</group>;
}

const WAR = [
  [-4.6, 0, -1.6],
  [-1.9, 0, -4.1],
  [1.9, 0, -4.1],
  [4.6, 0, -1.6],
];

export default function World({ scroll }) {
  return (
    <>
      <color attach="background" args={["#05050a"]} />
      <fog attach="fog" args={["#05050a", 13, 48]} />

      {/* lighting */}
      <ambientLight intensity={0.35} />
      <spotLight position={[0, 12, 6]} angle={0.5} penumbra={0.8} intensity={2.2} color="#cfefff" />
      <pointLight position={[-8, 5, -6]} intensity={1.1} color="#00FF66" />
      <pointLight position={[9, 4, 8]} intensity={1.2} color="#37a2ff" />

      {/* floor + atmosphere (persistent world) */}
      <Grid
        position={[0, 0, 0]}
        args={[80, 80]}
        cellSize={1}
        cellThickness={0.55}
        cellColor="#0d2740"
        sectionSize={5}
        sectionThickness={1}
        sectionColor="#123f68"
        fadeDistance={46}
        fadeStrength={2}
        infiniteGrid
      />
      <Sparkles count={44} scale={[26, 10, 26]} position={[0, 4, -6]} size={1.4} speed={0.25} color="#00E5FF" opacity={0.25} />

      {/* persistent AI core */}
      <Float speed={0.8} rotationIntensity={0.1} floatIntensity={0.25}>
        <Monolith />
      </Float>

      {/* 01 — the request: requirement shards */}
      <Scene scroll={scroll} index={1} half={0.7}>
        {[
          [-2.1, 2.5, 2.4, -0.18],
          [-1.05, 3.0, 2.7, -0.08],
          [0.05, 2.6, 3.0, 0],
          [1.15, 3.05, 2.7, 0.08],
          [2.2, 2.55, 2.4, 0.18],
        ].map((s, i) => (
          <Shard key={i} position={[s[0], s[1], s[2]]} rotation={[0, s[3], 0]} />
        ))}
        <Beam from={[0, 2.4, 0.3]} to={[0.05, 2.6, 3.0]} speed={0.8} />
      </Scene>

      {/* 02 — market discovery */}
      <Scene scroll={scroll} index={2} half={0.85} rise={0}>
        <MarketField scroll={scroll} />
      </Scene>

      {/* 03 — supplier intelligence cluster */}
      <Scene scroll={scroll} index={3} half={0.72}>
        {[
          [-6, 0, -7, "#00E5FF"],
          [-4.4, 0, -8.6, "#37a2ff"],
          [-3, 0, -6.4, "#00FF66"],
          [-6.6, 0, -9.1, "#2f7bff"],
          [-4.1, 0, -6, "#00E5FF"],
        ].map((k, i) => (
          <Kiosk key={i} position={[k[0], k[1], k[2]]} color={k[3]} dim={i > 2} />
        ))}
      </Scene>

      {/* 04 — verification: one supplier's data flows into the core */}
      <Scene scroll={scroll} index={4} half={0.66}>
        <Kiosk position={[2.5, 0, 0.4]} color="#00E5FF" />
        <Beam from={[2.5, 1.0, 0.6]} to={[0.4, 2.0, 0.3]} speed={1.1} />
        <Beam from={[2.5, 0.7, 0.6]} to={[0.4, 1.4, 0.3]} speed={0.8} color="#00FF66" />
      </Scene>

      {/* 05 — negotiation (hero): AI vs supplier */}
      <Scene scroll={scroll} index={5} half={0.7}>
        <Kiosk position={[3.5, 0, -0.3]} color="#37a2ff" scale={1.15} />
        <Beam from={[0.5, 2.0, 0]} to={[3.5, 1.1, -0.3]} speed={0.9} />
      </Scene>

      {/* 06 — multi-vendor war room */}
      <Scene scroll={scroll} index={6} half={0.72}>
        {WAR.map((p, i) => (
          <React.Fragment key={i}>
            <Kiosk position={p} color={i === 1 ? "#00FF66" : "#2f7bff"} dim={i === 2} />
            <Beam from={[0, 1.9, 0]} to={[p[0], 1.0, p[2]]} color={i === 1 ? "#00FF66" : "#00E5FF"} speed={0.6 + i * 0.1} />
          </React.Fragment>
        ))}
      </Scene>

      {/* 07 — true landed cost */}
      <Scene scroll={scroll} index={7} half={0.66} rise={0}>
        <CostTower scroll={scroll} position={[5, 0, 1]} />
      </Scene>

      {/* 08 — recommendation: hero supplier dominant, others dim */}
      <Scene scroll={scroll} index={8} half={0.66}>
        <Kiosk position={[2.2, 0, -1]} color="#00FF66" scale={1.35} />
        <Kiosk position={[-2.6, 0, -1.4]} color="#2f7bff" scale={0.9} dim />
        <Kiosk position={[-1, 0, -3]} color="#2f7bff" scale={0.9} dim />
        <Beam from={[0.4, 2.0, 0]} to={[2.2, 1.2, -1]} color="#00FF66" speed={1} />
      </Scene>

      {/* 09 — human decision (calm) */}
      <Scene scroll={scroll} index={9} half={0.66}>
        <Kiosk position={[2.2, 0, -1]} color="#00FF66" scale={1.35} />
      </Scene>

      {/* 10 — mission complete */}
      <Scene scroll={scroll} index={10} half={0.7}>
        <Kiosk position={[2.2, 0, -1]} color="#00FF66" scale={1.2} />
        <Beam from={[0.4, 2.0, 0]} to={[2.2, 1.1, -1]} color="#00FF66" speed={0.7} />
      </Scene>
      <SealRing scroll={scroll} />
    </>
  );
}
