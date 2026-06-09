/**
 * placementPolicy.ts — 拖拽放置策略
 *
 * 规则：
 *   1. 自动吸附到最近的已占用时隙边界（±SNAP_THRESHOLD 像素内）
 *   2. 智能避让已有模块（自动后移或前移）
 *   3. 时间线边界约束（不允许 start_time < 0 或超出总时长）
 *   4. 返回最佳插入位置和需要偏移量
 */

export interface ModuleSlot {
  index: number;
  id: string;
  startTime: number;
  duration: number;
  isDragging: boolean;
  x?: number;  // screen coord
  width?: number; // screen coord
}

export interface PlacementResult {
  insertIndex: number;   // where to insert in the array
  startTime: number;     // calculated start_time for the moved module
  shiftSlots: Array<{ index: number; newStart: number }>; // modules that need shifting
}

const SNAP_THRESHOLD = 8;  // pixels

/**
 * Calculate optimal placement given the current drag X position.
 *
 * @param clientX  - current mouse X (relative to timeline track)
 * @param slots    - all current modules on the track (sorted by start_time)
 * @param dragIdx  - index of the dragged module in slots
 * @param duration - duration of the dragged module
 * @param pxPerSec - pixels per second scale
 * @param maxTime  - maximum allowed time (total video duration)
 */
export function computePlacement(
  clientX: number,
  slots: ModuleSlot[],
  dragIdx: number,
  duration: number,
  pxPerSec: number,
  maxTime: number,
): PlacementResult {
  const rawTime = Math.max(0, clientX / pxPerSec);
  let targetTime = Math.min(rawTime, Math.max(0, maxTime - duration));

  // Build sorted slots excluding the dragged one
  const others = slots
    .filter((_, i) => i !== dragIdx)
    .sort((a, b) => a.startTime - b.startTime);

  // Snap to nearest slot boundary
  for (const slot of others) {
    const slotEndPx = (slot.startTime + slot.duration) * pxPerSec;
    const slotStartPx = slot.startTime * pxPerSec;
    if (Math.abs(clientX - slotEndPx) < SNAP_THRESHOLD) {
      targetTime = slot.startTime + slot.duration;
      break;
    }
    if (Math.abs(clientX - slotStartPx) < SNAP_THRESHOLD) {
      targetTime = slot.startTime;
      break;
    }
  }

  // Collision avoidance: find position where no overlap
  let insertIdx = 0;
  const shiftSlots: PlacementResult['shiftSlots'] = [];

  for (let i = 0; i <= others.length; i++) {
    const prev = others[i - 1];
    const next = others[i];

    const minStart = prev ? prev.startTime + prev.duration : 0;
    const maxEnd = next ? next.startTime : maxTime;
    const roomEnd = maxEnd - duration;

    if (targetTime >= minStart && targetTime <= roomEnd) {
      // Fits here
      insertIdx = i;
      break;
    }

    if (i < others.length && targetTime < others[i].startTime) {
      // Might need to push later modules
      let pushedTime = targetTime + duration;
      for (let j = i; j < others.length; j++) {
        if (others[j].startTime < pushedTime) {
          shiftSlots.push({
            index: others[j].isDragging ? -1 : j,
            newStart: pushedTime,
          });
          pushedTime = others[j].startTime + others[j].duration;
        } else {
          break;
        }
      }
      insertIdx = i;
      break;
    }
  }

  return { insertIndex: insertIdx, startTime: targetTime, shiftSlots };
}
