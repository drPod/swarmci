// Adapted from tiny-browser-agent (Apache-2.0). Modified for SwarmCI.
// See vendor/NOTICE.md and vendor/tiny-browser-agent-LICENSE.
function renderArtifactCard(label, href, kind = 'image') {
  if (!href) return '';
  const safeLabel = esc(label);
  const safeHref = esc(href);
  const media = kind === 'video'
    ? `<video controls preload="metadata" src="${safeHref}"></video>`
    : `<a target="_blank" rel="noreferrer" href="${safeHref}"><img src="${safeHref}" alt="${safeLabel} screenshot"></a>`;
  return `<div class="artifact-card"><div class="artifact-label">${safeLabel} · <a class="artifact-link" target="_blank" rel="noreferrer" href="${safeHref}">open</a></div>${media}</div>`;
}

function renderActionReplayCard(label, href) {
  if (!href) return '';
  const safeLabel = esc(label || 'Action replay');
  const safeHref = esc(href);
  return `<div class="artifact-primary"><div class="artifact-card"><div class="artifact-label">${safeLabel} · <a class="artifact-link" target="_blank" rel="noreferrer" href="${safeHref}">open</a></div><a target="_blank" rel="noreferrer" href="${safeHref}"><img src="${safeHref}" alt="${safeLabel}"></a></div></div>`;
}

function renderBeforeAfterCompare(beforeHref, afterHref) {
  if (!beforeHref && !afterHref) return '';
  if (!beforeHref || !afterHref) {
    const label = beforeHref ? 'Before screenshot' : 'After screenshot';
    return renderArtifactCard(label, beforeHref || afterHref);
  }
  // P5: slider overlay. The "after" image stacks on top and a CSS clip-path
  // tied to a range input reveals the "before" underneath as the user drags.
  const before = esc(beforeHref);
  const after = esc(afterHref);
  return `
    <div class="artifact-compare-control">
      <div class="artifact-compare-title">Compare · <a class="artifact-link" target="_blank" rel="noreferrer" href="${before}">open before</a> · <a class="artifact-link" target="_blank" rel="noreferrer" href="${after}">open after</a></div>
      <div class="artifact-slider" style="--split:50%">
        <img class="artifact-slider-before" src="${before}" alt="Before screenshot">
        <img class="artifact-slider-after" src="${after}" alt="After screenshot">
        <input class="artifact-slider-range" type="range" min="0" max="100" value="50" aria-label="Before/after slider"
          data-compare-slider>
      </div>
    </div>`;
}
