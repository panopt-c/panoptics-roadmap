/**
 * Story hooks — when the campaign's narrative spine plays (docs/GAME_DESIGN.md §9, cutscene plan).
 *
 *   prologue   once, the first time the hub is entered (boot → prologue → hub)
 *   intro-<t>  once, before the first deploy of sector t's first level (hub → intro → mission)
 *   epilogue   once, after the campaign's last victory screen (victory/cutscene → epilogue → hub)
 *
 * Every story scene plays on the regular cutscene screen (`go('cutscene', {mission: payload,
 * story: id, then})`), so it looks, skips and respects reduced motion exactly like a boss
 * transmission. The cutscene screen marks the scene seen when it finishes — played through or
 * skipped — and then goes to `then`.
 *
 * Seen flags live in the save (`State.story`, POST /api/story/seen). A local set remembers what
 * this tab already marked, so a `state` push that raced the POST can never replay a scene.
 *
 * Old backends have no `State.story`: then nothing here fires and no request is sent. A story
 * request that fails at play time is skipped silently: the player goes straight to `then`.
 */

export const STORY_IDS = Object.freeze(['prologue', 'intro-0', 'intro-1', 'intro-2', 'intro-3', 'intro-4', 'epilogue']);
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];

const marked = new Set(); // ids this tab has marked seen (survives a stale State push)

/** `State.story`, or null when the server has no story support. */
export function storyState(ctx) {
  const story = ctx?.state?.story;
  return story && typeof story === 'object' && !Array.isArray(story) ? story : null;
}

export function isSeen(ctx, id) {
  if (marked.has(id)) return true;
  const story = storyState(ctx);
  if (!story) return false;
  if (id === 'prologue') return story.prologue === true;
  if (id === 'epilogue') return story.epilogue === true;
  const tier = introTier(id);
  return tier !== null && Array.isArray(story.intros) && story.intros.includes(tier);
}

/** 'intro-3' → 3; anything else → null. */
export function introTier(id) {
  const m = /^intro-(\d)$/.exec(String(id));
  return m ? Number(m[1]) : null;
}

/** "ACT IV" for tier 3. */
export function actName(tier) {
  return `ACT ${ROMAN[tier] ?? tier + 1}`;
}

/** True when the prologue should play on this hub entry. */
export function needsPrologue(ctx) {
  return !!storyState(ctx) && !isSeen(ctx, 'prologue');
}

/** The act opening to play before deploying `levelId`, or null. */
export function pendingIntro(ctx, levelId) {
  if (!storyState(ctx)) return null;
  for (const sector of ctx.state.campaign || []) {
    const first = sector?.levels?.[0];
    if (!first || first.id !== levelId) continue;
    if (first.status !== 'current') return null; // only the first deploy of a level not yet cleared
    const id = `intro-${sector.tier}`;
    return STORY_IDS.includes(id) && !isSeen(ctx, id) ? id : null;
  }
  return null;
}

/** True when the campaign is complete and its epilogue has not played yet. */
export function needsEpilogue(ctx) {
  const state = ctx?.state;
  if (!storyState(ctx) || isSeen(ctx, 'epilogue') || !state) return false;
  return state.current === null && allCleared(state);
}

function allCleared(state) {
  const levels = (state.campaign || []).flatMap((s) => s?.levels || []);
  return levels.length > 0 && levels.every((l) => l.status === 'cleared');
}

/**
 * Every story scene for the hub's STORY archive, in play order:
 * {id, chapter, tier, sector, unlocked, seen}. A scene is unlocked once it played, or once the
 * player is past the point where it plays (older saves that predate the story hooks).
 */
export function storyIndex(ctx) {
  const state = ctx?.state || {};
  const campaign = state.campaign || [];
  return STORY_IDS.map((id) => {
    const seen = isSeen(ctx, id);
    const tier = introTier(id);
    if (tier === null) {
      const unlocked = id === 'prologue' ? true : seen || (state.current === null && allCleared(state));
      return { id, chapter: id.toUpperCase(), tier: null, sector: null, unlocked, seen };
    }
    const sector = campaign.find((s) => s?.tier === tier) || null;
    const reached = !!sector?.levels?.some((l) => l.status === 'cleared');
    return { id, chapter: actName(tier), tier, sector, unlocked: seen || reached, seen };
  });
}

/**
 * Play a story scene on the cutscene screen, then go to `then` ({name, params}). Any failure
 * (old backend, link lost, malformed payload) skips the scene: the player goes straight on.
 * `cached` is a payload the caller already holds (the hub's archive), saving a request.
 */
export async function playStory(ctx, id, then = { name: 'hub', params: {} }, cached = null) {
  const next = { name: then?.name || 'hub', params: then?.params || {} };
  let payload = playable(cached) ? cached : null;
  if (!payload) {
    try {
      payload = await ctx.api.story(id);
    } catch {
      payload = null;
    }
  }
  if (!playable(payload)) return ctx.screens.go(next.name, next.params);
  return ctx.screens.go('cutscene', { mission: payload, story: id, then: next });
}

/** A payload the cutscene screen can play: an object with at least one narration line. */
function playable(payload) {
  const narration = payload?.cutscene?.narration;
  return !!payload && typeof payload === 'object' && Array.isArray(narration) && narration.length > 0;
}

/** Record that a scene was shown (played through or skipped). Never throws. */
export function markSeen(ctx, id) {
  if (!STORY_IDS.includes(id)) return Promise.resolve(false);
  marked.add(id);
  const story = storyState(ctx);
  if (story) patch(story, id);
  if (!story || typeof ctx.api?.storySeen !== 'function') return Promise.resolve(false);
  return ctx.api
    .storySeen(id)
    .then((reply) => {
      const fresh = reply?.story;
      if (fresh && typeof fresh === 'object' && ctx.state) ctx.state.story = fresh;
      return true;
    })
    .catch(() => false);
}

function patch(story, id) {
  if (id === 'prologue') story.prologue = true;
  else if (id === 'epilogue') story.epilogue = true;
  else {
    const tier = introTier(id);
    const intros = Array.isArray(story.intros) ? story.intros : (story.intros = []);
    if (tier !== null && !intros.includes(tier)) {
      intros.push(tier);
      intros.sort((a, b) => a - b);
    }
  }
}

/** Test hook: forget what this tab marked. */
export function _resetStoryMarks() {
  marked.clear();
}
