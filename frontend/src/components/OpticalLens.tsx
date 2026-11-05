import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { MeshTransmissionMaterial } from '@react-three/drei/core/MeshTransmissionMaterial.js';
import { Text } from '@react-three/drei/core/Text.js';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ComponentRef, RefObject } from 'react';
import { Color, MathUtils, SphereGeometry } from 'three';
import type { Group, ShaderMaterial } from 'three';
import font from '@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-600-normal.woff?url';
import type { LensMotion } from './InspectionHero';

interface SceneProps {
  ip: string;
  stage: RefObject<HTMLElement | null>;
  address: RefObject<HTMLHeadingElement | null>;
  floating: RefObject<HTMLDivElement | null>;
  motion: RefObject<LensMotion>;
}

const glassBackground = new Color('#09090b');
const lensLerp = 0.1;

function LensScene({ ip, stage, address, floating, motion }: SceneProps) {
  const invalidate = useThree((state) => state.invalidate);
  const size = useThree((state) => state.size);
  const lens = useRef<Group>(null);
  const body = useRef<ComponentRef<typeof MeshTransmissionMaterial>>(null);
  const rim = useRef<ShaderMaterial>(null);
  const [type, setType] = useState({ x: 0, y: 0, size: 0, spacing: 0 });
  const synced = useRef(false);
  const [radius, setRadius] = useState(100);
  const geometry = useMemo(() => new SphereGeometry(1, 48, 32).scale(radius, radius, 15), [radius]);
  const grid = useMemo(
    () => ({
      width: { value: size.width },
      height: { value: size.height },
      ground: { value: glassBackground },
      dotColor: { value: new Color('#303034') },
    }),
    [size.width, size.height],
  );

  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => {
    motion.current.invalidate = invalidate;
    return () => {
      delete motion.current.invalidate;
    };
  }, [motion, invalidate]);

  useEffect(() => {
    const element = address.current;
    const host = stage.current;
    if (!element || !host) return;
    synced.current = false;
    delete host.dataset.glassReady;
    const measure = () => {
      const bounds = host.getBoundingClientRect();
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      const fontSize = Number.parseFloat(style.fontSize);
      setType({
        x: rect.left + rect.width / 2 - bounds.left - bounds.width / 2,
        y: bounds.height / 2 - (rect.top + rect.height / 2 - bounds.top),
        size: fontSize,
        spacing: Number.parseFloat(style.letterSpacing) / fontSize || 0,
      });
      const nextRadius = bounds.width < 650 ? 94 : 111;
      setRadius(nextRadius);
      host.style.setProperty('--lens-size', `${nextRadius * 2}px`);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    observer.observe(host);
    measure();
    return () => {
      observer.disconnect();
      delete host.dataset.glassReady;
      host.style.removeProperty('--lens-size');
      floating.current?.style.removeProperty('transform');
      floating.current?.removeAttribute('data-aligned');
    };
  }, [address, stage, floating]);

  const markTextReady = useCallback(() => {
    synced.current = true;
    invalidate();
  }, [invalidate]);

  useFrame((_, delta) => {
    const glass = lens.current;
    const host = stage.current;
    const bodyMaterial = body.current;
    const rimMaterial = rim.current;
    if (!glass || !host || !bodyMaterial || !rimMaterial || !synced.current || !type.size) return;
    if (!host.dataset.glassReady) host.dataset.glassReady = 'true';

    const centerX = size.width / 2 + type.x;
    const centerY = size.height / 2 - type.y;
    const { target, pinned } = motion.current;
    const point = pinned ? { x: centerX, y: centerY } : target;
    const x = point
      ? MathUtils.clamp(point.x, radius, size.width - radius) - size.width / 2
      : glass.position.x;
    const y = point
      ? size.height / 2 - MathUtils.clamp(point.y, radius, size.height - radius)
      : glass.position.y;
    const tiltX = point && !pinned ? (y / size.height) * -0.44 : 0;
    const tiltY = point && !pinned ? (x / size.width) * 0.44 : 0;
    const step = Math.min(delta || 1 / 60, 1 / 30);
    // Keep the same easing at different display refresh rates.
    const blend = 1 - (1 - lensLerp) ** (step * 60);
    glass.position.x = MathUtils.lerp(glass.position.x, x, blend);
    glass.position.y = MathUtils.lerp(glass.position.y, y, blend);
    glass.rotation.x = MathUtils.lerp(glass.rotation.x, tiltX, blend);
    glass.rotation.y = MathUtils.lerp(glass.rotation.y, tiltY, blend);
    const targetScale = point ? 1 : 0;
    const nextScale = MathUtils.lerp(glass.scale.x, targetScale, blend);
    const scale = Math.abs(nextScale - targetScale) < 0.005 ? targetScale : nextScale;
    glass.scale.setScalar(scale);
    glass.visible = scale > 0;
    bodyMaterial.visible = glass.visible;
    bodyMaterial.opacity = scale;
    rimMaterial.uniforms.fade.value = scale;

    const floatingElement = floating.current;
    const distance = Math.abs(glass.position.x - x) + Math.abs(glass.position.y - y);
    if (floatingElement && glass.visible) {
      floatingElement.style.transform = `translate3d(${glass.position.x + size.width / 2}px, ${size.height / 2 - glass.position.y}px, 0) translate(-50%, -50%)`;
      if (scale >= 0.85 && distance <= 28 && !floatingElement.hasAttribute('data-aligned')) {
        floatingElement.setAttribute('data-aligned', '');
      }
    }
    const rotationGap = Math.abs(glass.rotation.x - tiltX) + Math.abs(glass.rotation.y - tiltY);
    if (scale !== targetScale || (point && (distance > 0.35 || rotationGap > 0.002))) invalidate();
  });

  return (
    <>
      <mesh position={[0, 0, -100]}>
        <planeGeometry args={[size.width, size.height]} />
        <shaderMaterial
          uniforms={grid}
          vertexShader={`
            varying vec2 vUv;
            void main() {
              vUv = uv;
              gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
          `}
          fragmentShader={`
            varying vec2 vUv;
            uniform float width;
            uniform float height;
            uniform vec3 ground;
            uniform vec3 dotColor;
            void main() {
              vec2 center = vUv - 0.5;
              vec2 cell = mod(center * vec2(width, height) + 10.0, 20.0) - 10.0;
              float dotMask = 1.0 - smoothstep(0.45, 1.25, length(cell));
              float fade = 1.0 - smoothstep(0.08, 0.48, length(center));
              gl_FragColor = vec4(mix(ground, dotColor, dotMask * fade), 1.0);
              #include <colorspace_fragment>
            }
          `}
        />
      </mesh>
      {type.size > 0 && (
        <Text
          font={font}
          fontSize={type.size}
          letterSpacing={type.spacing}
          characters="0123456789."
          anchorX="center"
          anchorY="middle"
          position={[type.x, type.y, 0]}
          color="#f5f5f7"
          onSync={markTextReady}
        >
          {ip}
        </Text>
      )}
      <group ref={lens} position={[0, 0, 55]} scale={0} visible={false}>
        <mesh geometry={geometry}>
          <MeshTransmissionMaterial
            ref={body}
            transparent
            visible={false}
            opacity={0}
            background={glassBackground}
            transmission={1}
            thickness={36}
            ior={1.22}
            roughness={0.075}
            chromaticAberration={0.018}
            anisotropicBlur={0.025}
            distortion={0}
            samples={3}
            resolution={384}
          />
        </mesh>
        <mesh geometry={geometry} scale={1.001} renderOrder={2}>
          <shaderMaterial
            ref={rim}
            transparent
            depthWrite={false}
            uniforms={{ radius: { value: radius }, fade: { value: 0 } }}
            vertexShader={`
              uniform float radius;
              varying vec2 vSurface;
              void main() {
                vSurface = position.xy / radius;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
              }
            `}
            fragmentShader={`
              uniform float fade;
              varying vec2 vSurface;
              void main() {
                float r = length(vSurface);
                vec2 direction = vSurface / max(r, 0.01);
                float key = max(0.0, dot(direction, vec2(-0.60, 0.8)));
                float edge = smoothstep(0.967, 1.0, r);
                float highlight = (r - 0.938) * 42.0;
                float rim = (r - 0.973) * 80.0;
                float reflection = exp(-highlight * highlight) * pow(key, 3.0);
                float bounce = exp(-rim * rim) * pow(max(0.0, dot(direction, vec2(0.8, -0.6))), 5.0);
                float alpha = edge * (0.16 + key * 0.28) + reflection * 0.25 + bounce * 0.18;
                gl_FragColor = vec4(vec3(0.71, 0.87, 0.93), alpha * fade);
                #include <colorspace_fragment>
              }
            `}
          />
        </mesh>
      </group>
    </>
  );
}

export default function OpticalLens(props: SceneProps) {
  const [lost, setLost] = useState(false);
  const canvas = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrapper = canvas.current;
    const host = props.stage.current;
    const recover = () => {
      if (host) delete host.dataset.glassReady;
      setLost(true);
    };
    wrapper?.addEventListener('webglcontextlost', recover, true);
    return () => wrapper?.removeEventListener('webglcontextlost', recover, true);
  }, [props.stage]);

  if (lost) return null;
  return (
    <div className="inspection-canvas" ref={canvas} aria-hidden="true">
      <Canvas
        flat
        style={{ pointerEvents: 'none' }}
        orthographic
        camera={{ position: [0, 0, 500], near: 0.1, far: 1000 }}
        dpr={[1, 1.25]}
        frameloop="demand"
        gl={{ alpha: true, antialias: true }}
        fallback={null}
      >
        <LensScene {...props} />
      </Canvas>
    </div>
  );
}
