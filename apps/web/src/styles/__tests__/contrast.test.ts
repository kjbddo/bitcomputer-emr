import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const TOKENS_PATH = resolve(__dirname, "../tokens.css");
const css = readFileSync(TOKENS_PATH, "utf8");

const LIGHT_MARKER = ":root {";
const MEDIA_MARKER = "@media (prefers-color-scheme: dark) {";
const DARK_MARKER = ':root[data-theme="dark"] {';

/** marker 뒤 첫 `{` 부터 짝이 맞는 `}` 까지의 본문을 돌려준다. */
function blockAfter(source: string, marker: string): string {
  const start = source.indexOf(marker);
  if (start === -1) {
    throw new Error(`tokens.css 에서 마커를 찾지 못했습니다: ${marker}`);
  }
  const open = source.indexOf("{", start + marker.length - 1);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(open + 1, i);
    }
  }
  throw new Error(`블록이 닫히지 않았습니다: ${marker}`);
}

function declarations(block: string): Record<string, string> {
  const out: Record<string, string> = {};
  const re = /--([\w-]+)\s*:\s*([^;]+);/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(block)) !== null) {
    out[m[1]] = m[2].trim();
  }
  return out;
}

const lightDecls = declarations(blockAfter(css, LIGHT_MARKER));
const mediaDecls = declarations(blockAfter(css, MEDIA_MARKER));
const darkDecls = declarations(blockAfter(css, DARK_MARKER));

/** `var(--x)` 를 원시 램프(:root 에만 존재)까지 따라가 hex 로 만든다. */
function resolveToken(themeDecls: Record<string, string>, name: string, depth = 0): string {
  if (depth > 5) throw new Error(`토큰 참조가 너무 깊습니다: --${name}`);
  const raw = themeDecls[name] ?? lightDecls[name];
  if (raw === undefined) throw new Error(`정의되지 않은 토큰: --${name}`);
  const ref = /^var\(\s*--([\w-]+)\s*\)$/.exec(raw);
  if (ref) return resolveToken(lightDecls, ref[1], depth + 1);
  if (!/^#[0-9a-fA-F]{6}$/.test(raw)) {
    throw new Error(`hex 로 해석되지 않는 토큰: --${name} = ${raw}`);
  }
  return raw;
}

function relativeLuminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const linear = channels.map((c) =>
    c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  );
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

/** [전경, 배경, 최소대비] */
const PAIRS: Array<[string, string, number]> = [
  ["text-primary", "surface-canvas", 4.5],
  ["text-primary", "surface-raised", 4.5],
  ["text-primary", "surface-sunken", 4.5],
  ["text-primary", "surface-overlay", 4.5],
  ["text-secondary", "surface-raised", 4.5],
  ["text-secondary", "surface-canvas", 4.5],
  ["text-muted", "surface-raised", 4.5],
  ["text-muted", "surface-canvas", 4.5],
  ["text-on-chrome", "surface-chrome", 4.5],
  ["text-on-chrome", "surface-chrome-hover", 4.5],
  ["text-on-chrome", "surface-chrome-active", 4.5],
  ["text-on-fill", "accent-fill", 4.5],
  ["text-on-fill", "danger-fill", 4.5],
  ["accent-text", "surface-raised", 4.5],
  ["accent-text", "accent-bg", 4.5],
  ["success-text", "success-bg", 4.5],
  ["warning-text", "warning-bg", 4.5],
  ["danger-text", "danger-bg", 4.5],
  ["border-control", "surface-raised", 3.0],
  ["border-control", "surface-canvas", 3.0],
  ["focus-ring", "surface-raised", 3.0],
  ["focus-ring", "surface-canvas", 3.0],
];

const THEMES: Array<[string, Record<string, string>]> = [
  ["light", lightDecls],
  ["dark", darkDecls],
];

describe("디자인 토큰 대비비", () => {
  for (const [themeName, decls] of THEMES) {
    for (const [fg, bg, min] of PAIRS) {
      it(`${themeName}: --${fg} on --${bg} >= ${min}:1`, () => {
        const ratio = contrastRatio(resolveToken(decls, fg), resolveToken(decls, bg));
        expect(ratio).toBeGreaterThanOrEqual(min);
      });
    }
  }
});

describe("다크 토큰 두 블록 일치", () => {
  it("미디어 쿼리 블록과 [data-theme=dark] 블록이 같은 토큰을 같은 값으로 선언한다", () => {
    expect(Object.keys(mediaDecls).sort()).toEqual(Object.keys(darkDecls).sort());
    for (const key of Object.keys(darkDecls)) {
      expect(`${key}=${mediaDecls[key]}`).toBe(`${key}=${darkDecls[key]}`);
    }
  });

  it("다크 블록이 라이트에 있는 의미 토큰을 빠짐없이 재정의한다", () => {
    const semantic = Object.keys(lightDecls).filter((k) => lightDecls[k].startsWith("var("));
    const missing = semantic.filter((k) => !(k in darkDecls));
    expect(missing).toEqual([]);
  });
});
