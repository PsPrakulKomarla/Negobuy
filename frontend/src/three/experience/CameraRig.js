import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { CAM, SCENES, clamp, lerp } from "./helpers";

export default function CameraRig({ scroll }) {
  const look = useRef(new THREE.Vector3(0, 1.7, 0));
  const tp = useRef(new THREE.Vector3());
  const tl = useRef(new THREE.Vector3());
  useFrame((state, delta) => {
    const sp = clamp(scroll.get(), 0, 1) * (SCENES - 1);
    const i = Math.min(SCENES - 2, Math.floor(sp));
    const f = sp - i;
    const A = CAM[i];
    const B = CAM[i + 1];
    tp.current.set(
      lerp(A.pos[0], B.pos[0], f),
      lerp(A.pos[1], B.pos[1], f),
      lerp(A.pos[2], B.pos[2], f)
    );
    tl.current.set(
      lerp(A.look[0], B.look[0], f),
      lerp(A.look[1], B.look[1], f),
      lerp(A.look[2], B.look[2], f)
    );
    // subtle cinematic idle drift
    const t = state.clock.elapsedTime;
    tp.current.x += Math.sin(t * 0.15) * 0.18;
    tp.current.y += Math.cos(t * 0.12) * 0.12;

    const k = Math.min(1, delta * 2.6);
    state.camera.position.lerp(tp.current, k);
    look.current.lerp(tl.current, k);
    state.camera.lookAt(look.current);
  });
  return null;
}
