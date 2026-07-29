/* =====================================================================
 * CCNA Quest - キャラクター立ち絵ジェネレータ (萌え系アニメ SVG) v2
 * 大きく鋭い瞳・濃いまつ毛・大きなハイライト・流れる毛束で萌え寄りに。
 * Art.face(style, mood, opts)
 *   style = { skin, hair, hair2, eyes, hairstyle, eyetype, accessory, ahoge, outfit }
 *     eyetype: sharp(つり目) | round(まる目) | gentle(たれ目)
 *   mood  = normal | happy | shy | sad | annoyed | love | surprised
 * ===================================================================== */

Art._fid = Art._fid || 0;

Art.face = function (style, mood = "normal", opts = {}) {
  const s = Object.assign({
    skin: "#ffe4d6", hair: "#5b4636", hair2: "#3f3025", eyes: "#6b4a2b",
    hairstyle: "long", eyetype: "round", accessory: null, ahoge: false, outfit: "#64748b",
  }, style || {});
  const bg = opts.bg || null;
  const uid = ++Art._fid;
  const dark = shade(s.hair, 55), hi = light(s.hair, 70), lash = "#241a1e";
  const irisTop = light(s.eyes, 55), irisBot = shade(s.eyes, 55);

  /* ---------- 瞳 ---------- */
  const eye = (cx, dir) => {
    // dir: +1=右目(外側=右) / -1=左目
    if (mood === "happy") // 嬉しい閉じ目( ^ )
      return `<path d="M${cx - 16} 150 Q${cx} 132 ${cx + 16} 150" stroke="${lash}" stroke-width="4.5" fill="none" stroke-linecap="round"/>
              <path d="M${cx - 12} 158 q12 6 24 0" stroke="${lash}" stroke-width="2" fill="none" stroke-linecap="round" opacity=".5"/>`;
    const w = 18, h = mood === "surprised" ? 26 : 22;
    const lidTopY = mood === "shy" || mood === "sad" ? 138 : 128; // 半目/伏し目
    const flick = s.eyetype === "sharp" ? -8 : s.eyetype === "gentle" ? 8 : 0; // 外側の跳ね
    // 目の輪郭(アーモンド)
    const almond = `M${cx - dir * w} ${146}
      C${cx - dir * w} ${132} ${cx - dir * w * 0.3} ${lidTopY} ${cx + dir * 2} ${lidTopY}
      C${cx + dir * w * 0.6} ${lidTopY} ${cx + dir * w} ${132 + flick} ${cx + dir * w} ${146 + flick}
      C${cx + dir * w} ${158} ${cx + dir * w * 0.4} ${146 + h * 0.5} ${cx} ${146 + h * 0.5}
      C${cx - dir * w * 0.6} ${146 + h * 0.5} ${cx - dir * w} ${156} ${cx - dir * w} ${146} Z`;
    const clip = `eclip${uid}${dir > 0 ? "r" : "l"}`;
    const irisY = mood === "sad" ? 150 : 147;
    const heart = mood === "love"
      ? `<path d="M${cx} ${irisY + 6} l-9 -9 a5 5 0 0 1 9 -1 a5 5 0 0 1 9 1 z" fill="#ff4d79"/><circle cx="${cx - 3}" cy="${irisY - 3}" r="2.6" fill="#fff"/>`
      : `<circle cx="${cx}" cy="${irisY}" r="14" fill="url(#ir${uid})"/>
         <ellipse cx="${cx}" cy="${irisY + 6}" rx="12" ry="7" fill="${irisBot}" opacity=".5"/>
         <circle cx="${cx}" cy="${irisY + 1}" r="6.5" fill="#1c1016"/>
         <circle cx="${cx - 4}" cy="${irisY - 6}" r="5" fill="#fff"/>
         <circle cx="${cx + 5}" cy="${irisY + 5}" r="3" fill="#fff" opacity=".9"/>
         <ellipse cx="${cx}" cy="${irisY - 10}" rx="9" ry="3.5" fill="#fff" opacity=".35"/>`;
    return `<g>
      <defs><clipPath id="${clip}"><path d="${almond}"/></clipPath></defs>
      <path d="${almond}" fill="#fdfdff"/>
      <g clip-path="url(#${clip})">${heart}</g>
      <path d="M${cx - dir * w} ${146} C${cx - dir * w} ${131} ${cx - dir * w * 0.3} ${lidTopY - 1} ${cx + dir * 2} ${lidTopY - 1}
        C${cx + dir * w * 0.6} ${lidTopY - 1} ${cx + dir * w} ${131 + flick} ${cx + dir * w} ${146 + flick}"
        stroke="${lash}" stroke-width="5" fill="none" stroke-linecap="round"/>
      <path d="M${cx + dir * w} ${146 + flick} l${dir * 6} ${flick < 0 ? -6 : 2}" stroke="${lash}" stroke-width="4" stroke-linecap="round"/>
      ${s.eyetype === "gentle" ? `<path d="M${cx - dir * w * 0.6} ${146 + h * 0.5} q${dir * 8} 3 ${dir * 14} 0" stroke="${lash}" stroke-width="1.6" fill="none" opacity=".5"/>` : ""}
    </g>`;
  };

  /* ---------- 眉 ---------- */
  const browY = 113;
  const brow = (cx, dir) => {
    const shapes = {
      normal: `M${cx - 12} ${browY} q12 -4 24 0`,
      happy: `M${cx - 12} ${browY - 2} q12 -5 24 -1`,
      shy: `M${cx - 12} ${browY} q12 -3 24 1`,
      sad: `M${cx - 12} ${browY + 4} q12 6 24 8`.replace("q12 6 24 8", dir > 0 ? "q12 7 24 9" : "q12 5 24 3"),
      annoyed: `M${cx - 12} ${browY - 2} q12 6 24 ${dir > 0 ? 9 : 3}`,
      love: `M${cx - 12} ${browY - 2} q12 -5 24 -1`,
      surprised: `M${cx - 12} ${browY - 6} q12 -3 24 0`,
    };
    return `<path d="${shapes[mood] || shapes.normal}" stroke="${dark}" stroke-width="3" fill="none" stroke-linecap="round" opacity=".92"/>`;
  };

  /* ---------- 口 ---------- */
  const mouth = {
    normal: `<path d="M100 182 q10 7 20 0" stroke="#c65a70" stroke-width="2.6" fill="none" stroke-linecap="round"/>`,
    happy: `<path d="M98 180 q12 16 24 0 q-4 6 -12 6 q-8 0 -12 -6z" fill="#b83a55"/><path d="M101 181 q9 4 18 0" fill="#ff8fa0"/>`,
    shy: `<path d="M104 183 q6 5 12 0" stroke="#c65a70" stroke-width="2.6" fill="none" stroke-linecap="round"/>`,
    sad: `<path d="M102 187 q8 -6 16 0" stroke="#c65a70" stroke-width="2.6" fill="none" stroke-linecap="round"/>`,
    annoyed: `<path d="M104 186 q6 -3 12 -1" stroke="#c65a70" stroke-width="2.6" fill="none" stroke-linecap="round"/>`,
    love: `<path d="M100 181 q10 9 20 0" stroke="#b83a55" stroke-width="2.6" fill="none" stroke-linecap="round"/><path d="M103 183 q7 4 14 0" fill="#ff8fa0"/>`,
    surprised: `<ellipse cx="110" cy="186" rx="6" ry="8" fill="#9e3048"/>`,
  }[mood] || "";

  const blushOn = ["shy", "love", "happy"].includes(mood);
  const blush = blushOn
    ? `<g opacity="${mood === "love" ? .8 : .6}"><ellipse cx="76" cy="172" rx="13" ry="7" fill="#ff8a9a"/><ellipse cx="144" cy="172" rx="13" ry="7" fill="#ff8a9a"/>
       <path d="M70 170 h12 M72 175 h9" stroke="#ff6a80" stroke-width="1.4" opacity=".7"/><path d="M138 170 h12 M141 175 h9" stroke="#ff6a80" stroke-width="1.4" opacity=".7"/></g>`
    : "";

  const H = hairShapes(s.hairstyle, s.hair, dark, hi, uid);
  const ahoge = s.ahoge ? `<path d="M110 46 q-4 -18 8 -24 q-2 10 4 18" fill="none" stroke="${s.hair}" stroke-width="4" stroke-linecap="round"/>` : "";

  let acc = "";
  if (s.accessory === "glasses")
    acc = `<g fill="none" stroke="#2a2f3a" stroke-width="2.6"><rect x="66" y="134" width="34" height="28" rx="10"/><rect x="120" y="134" width="34" height="28" rx="10"/><path d="M100 146 h20"/></g>`;
  else if (s.accessory === "flower")
    acc = `<g transform="translate(66,72)">${flower("#ff5c8a")}</g>`;
  else if (s.accessory === "flowerG")
    acc = `<g transform="translate(66,72)">${flower("#8ee6a0")}</g>`;
  else if (s.accessory === "clip")
    acc = `<g><rect x="60" y="86" width="20" height="8" rx="4" fill="#ff5c8a"/><circle cx="70" cy="90" r="2.4" fill="#fff"/></g>`;
  else if (s.accessory === "cap")
    acc = `<path d="M56 78 Q110 44 164 78 L164 86 Q110 66 56 86 Z" fill="#2a2f3a"/><path d="M150 80 q20 2 24 12 l-24 0z" fill="#2a2f3a"/><circle cx="110" cy="60" r="6" fill="#c0392b"/>`;

  const sweat = mood === "surprised" ? `<path d="M158 96 q6 10 0 16 q-6 -6 0 -16z" fill="#7fd3ff" opacity=".85"/>` : "";
  const loveFx = mood === "love" ? `<text x="158" y="86" font-size="22">💕</text>` : "";

  return `<svg viewBox="0 0 220 260" class="face" preserveAspectRatio="xMidYMid meet" aria-label="キャラクター">
    <defs><linearGradient id="ir${uid}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${irisTop}"/><stop offset=".55" stop-color="${s.eyes}"/><stop offset="1" stop-color="${irisBot}"/>
    </linearGradient></defs>
    ${bg ? `<rect x="0" y="0" width="220" height="260" fill="${bg}"/>` : ""}
    <g class="face-bob">
      ${H.back}
      ${ahoge}
      <path d="M78 210 q32 -12 64 0 l10 46 h-84 z" fill="${s.outfit}"/>
      <path d="M96 196 h28 v18 q-14 8 -28 0 z" fill="${s.skin}"/>
      <path d="M60 96 C58 64 92 56 110 56 C128 56 162 64 160 96 C160 152 150 202 110 216 C70 202 60 152 60 96 Z" fill="${s.skin}"/>
      <ellipse cx="60" cy="150" rx="8" ry="12" fill="${s.skin}"/><ellipse cx="160" cy="150" rx="8" ry="12" fill="${s.skin}"/>
      <path d="M138 100 C154 116 152 168 118 208 C144 168 142 128 132 104 Z" fill="#c98" opacity=".12"/>
      ${H.side}
      ${eye(86, -1)}${eye(134, 1)}
      ${brow(86, -1)}${brow(134, 1)}
      <path d="M108 160 q4 6 -1 10" stroke="#e0a894" stroke-width="2" fill="none" stroke-linecap="round"/>
      ${blush}
      ${mouth}
      ${H.front}
      ${H.gloss}
      ${acc}
      ${sweat}${loveFx}
    </g>
  </svg>`;
};

/* 花アクセサリ */
function flower(c) {
  let p = "";
  for (let i = 0; i < 5; i++) { const a = i * 72 * Math.PI / 180; p += `<ellipse cx="${Math.cos(a) * 8}" cy="${Math.sin(a) * 8}" rx="5" ry="7" fill="${c}" transform="rotate(${i * 72})"/>`; }
  return `<g>${p}<circle r="4" fill="#ffe066"/></g>`;
}

/* 色ユーティリティ */
function shade(hex, d = 40) { const n = parseInt(hex.slice(1), 16); const r = Math.max(0, (n >> 16 & 255) - d), g = Math.max(0, (n >> 8 & 255) - d), b = Math.max(0, (n & 255) - d); return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1); }
function light(hex, d = 60) { const n = parseInt(hex.slice(1), 16); const r = Math.min(255, (n >> 16 & 255) + d), g = Math.min(255, (n >> 8 & 255) + d), b = Math.min(255, (n & 255) + d); return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1); }

/* ---------- 髪型 (背面 / サイド / 前髪 / ツヤ) ---------- */
function hairShapes(kind, c, dk, hi, uid) {
  // 前髪: とがった毛束(ジグザグ) 共通ベース
  const bangs = `<path d="M58 104 C54 58 92 46 110 46 C130 46 166 58 162 106
      C156 84 150 92 142 74 L134 96 L126 72 L116 98 L110 74 L104 98 L94 72 L86 96 L78 74 C70 92 64 86 58 104 Z" fill="${c}"/>`;
  const gloss = `<path d="M78 72 Q110 58 142 74 Q120 66 110 66 Q92 66 78 72 Z" fill="${hi}" opacity=".55"/>
    <path d="M96 70 l-4 20 M118 70 l3 20 M108 68 l0 22" stroke="${hi}" stroke-width="2" opacity=".4" fill="none"/>`;
  const S = {
    long: {
      back: `<path d="M46 160 C34 92 48 48 110 48 C172 48 186 92 174 160 L174 236 L156 236 C160 150 158 104 158 104 L62 104 C62 104 60 150 64 236 L46 236 Z" fill="${dk}"/>`,
      side: `<path d="M56 104 C50 150 54 190 60 220 L74 216 C66 180 66 140 70 108 Z" fill="${c}"/>
             <path d="M164 104 C170 150 166 190 160 222 L146 216 C154 180 154 140 150 108 Z" fill="${c}"/>`,
      front: bangs, gloss,
    },
    twin: {
      back: `<path d="M52 100 C48 54 78 46 110 46 C142 46 172 54 168 100 L156 100 C156 74 138 62 110 62 C82 62 64 74 64 100 Z" fill="${dk}"/>
             <path d="M40 130 C28 140 26 190 40 224 C48 196 44 150 56 120 Z" fill="${dk}"/>
             <path d="M180 130 C192 140 194 190 180 224 C172 196 176 150 164 120 Z" fill="${dk}"/>
             <path d="M40 128 C30 138 30 180 40 210 C46 186 44 150 54 124 Z" fill="${c}"/>
             <path d="M180 128 C190 138 190 180 180 210 C174 186 176 150 166 124 Z" fill="${c}"/>`,
      side: `<path d="M56 104 C52 140 54 168 58 190 L70 186 C64 156 64 130 68 108 Z" fill="${c}"/>
             <path d="M164 104 C168 140 166 168 162 190 L150 186 C156 156 156 130 152 108 Z" fill="${c}"/>`,
      front: bangs, gloss,
    },
    sidepony: {
      back: `<path d="M50 150 C44 86 60 48 110 48 C160 48 176 86 170 150 L164 150 C164 100 150 96 110 96 C70 96 60 100 56 150 Z" fill="${dk}"/>
             <path d="M158 70 C188 84 196 150 176 214 C168 190 158 150 150 108 Z" fill="${dk}"/>
             <path d="M160 74 C184 88 190 148 174 204 C168 184 160 150 152 110 Z" fill="${c}"/>`,
      side: `<path d="M56 104 C50 150 54 186 60 214 L74 210 C66 176 66 138 70 108 Z" fill="${c}"/>`,
      front: bangs, gloss,
    },
    hime: { // 姫カット(ストレート+サイド直線)
      back: `<path d="M46 170 C36 92 50 48 110 48 C170 48 184 92 174 170 L174 234 L154 234 L158 104 L62 104 L66 234 L46 234 Z" fill="${dk}"/>`,
      side: `<path d="M56 104 L58 200 L76 200 L72 104 Z" fill="${c}"/><path d="M164 104 L162 200 L144 200 L148 104 Z" fill="${c}"/>`,
      front: `<path d="M56 106 C52 58 92 46 110 46 C128 46 168 58 164 106 C164 96 150 92 142 92 L138 100 L128 90 L120 100 L110 88 L100 100 L92 90 L82 100 L78 92 C70 92 56 96 56 106 Z" fill="${c}"/>`,
      gloss,
    },
    wavy: {
      back: `<path d="M42 164 C30 92 46 48 110 48 C174 48 190 92 178 164 C174 196 164 200 168 226 C158 204 168 182 160 164 C160 130 158 104 158 104 L62 104 C62 130 60 164 60 164 C52 182 62 204 52 226 C56 200 46 196 42 164 Z" fill="${dk}"/>`,
      side: `<path d="M56 104 C48 140 58 160 52 186 C64 172 66 140 70 108 Z" fill="${c}"/>
             <path d="M164 104 C172 140 162 160 168 186 C156 172 154 140 150 108 Z" fill="${c}"/>`,
      front: bangs, gloss,
    },
  };
  return S[kind] || S.long;
}
