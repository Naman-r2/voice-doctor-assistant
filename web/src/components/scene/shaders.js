// GLSL for the particle sphere. Kept apart from the scene code so both stay readable.

// Simplex noise (Ashima Arts / Ian McEwan, MIT licence).
const NOISE = /* glsl */ `
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
float snoise(vec3 v) {
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0)) + i.y + vec4(0.0, i1.y, i2.y, 1.0)) + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}
`;

export const sphereVertex = /* glsl */ `
${NOISE}
uniform float uTime;
uniform float uEnergy;   // how loud the voice is, 0..1
uniform float uTwist;    // thinking: the sphere winds up
uniform float uScatter;  // 0 = a sphere, 1 = blown apart
uniform float uBurst;    // a booking just landed, 1 fading to 0
uniform float uPixelRatio;
uniform float uScale;

attribute float aSeed;
attribute vec3 aScatter;

varying float vShade;
varying float vSeed;

void main() {
  vec3 dir = normalize(position);

  // wind the sphere around its axis
  float angle = dir.y * uTwist;
  float c = cos(angle), s = sin(angle);
  dir = vec3(dir.x * c - dir.z * s, dir.y, dir.x * s + dir.z * c);

  // slow swell, plus sharp spikes that follow the voice
  float swell = snoise(dir * 1.4 + uTime * 0.18);
  float fine = snoise(dir * 4.2 - uTime * 0.55);
  float spikes = pow(max(fine, 0.0), 2.0) * uEnergy * 0.75;
  float radius = 1.0 + swell * (0.07 + uEnergy * 0.16) + spikes;

  // a ring of light that runs pole to pole when something is booked
  float ring = smoothstep(0.16, 0.0, abs(dir.y - (1.0 - uBurst * 2.0))) * uBurst;
  radius += ring * 0.28;

  vec3 formed = dir * radius;
  vec3 scattered = aScatter * (1.0 + 0.15 * sin(uTime * 0.4 + aSeed * 6.28));
  vec3 p = mix(formed, scattered, uScatter * (0.55 + 0.45 * aSeed));

  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;

  vShade = swell * 0.5 + 0.5 + spikes * 1.6 + ring * 2.0;
  vSeed = aSeed;
  float size = (1.6 + aSeed * 2.2) * (1.0 + uEnergy * 1.4 + ring * 3.0);
  gl_PointSize = size * uPixelRatio * uScale / -mv.z;
}
`;

export const sphereFragment = /* glsl */ `
uniform vec3 uColorA;
uniform vec3 uColorB;
uniform float uAlpha;
varying float vShade;
varying float vSeed;

void main() {
  float d = length(gl_PointCoord - 0.5);
  float dot_ = smoothstep(0.5, 0.0, d);
  vec3 colour = mix(uColorA, uColorB, clamp(vShade * 0.9 + (vSeed - 0.5) * 0.35, 0.0, 1.0));
  gl_FragColor = vec4(colour, dot_ * dot_ * uAlpha * (0.35 + vSeed * 0.65));
}
`;

export const dustVertex = /* glsl */ `
uniform float uTime;
uniform float uPixelRatio;
attribute float aSeed;
varying float vSeed;
void main() {
  vec3 p = position;
  p.y += sin(uTime * 0.08 + aSeed * 40.0) * 0.6;
  p.x += cos(uTime * 0.06 + aSeed * 25.0) * 0.4;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  vSeed = aSeed;
  gl_PointSize = (1.0 + aSeed * 2.5) * uPixelRatio * 9.0 / -mv.z;
}
`;

export const dustFragment = /* glsl */ `
uniform float uTime;
varying float vSeed;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float twinkle = 0.5 + 0.5 * sin(uTime * (0.6 + vSeed) + vSeed * 30.0);
  gl_FragColor = vec4(vec3(0.82, 0.86, 1.0), smoothstep(0.5, 0.0, d) * 0.5 * twinkle);
}
`;
