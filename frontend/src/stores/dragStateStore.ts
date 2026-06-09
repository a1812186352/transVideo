import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

export interface DragState {
  moduleId: string;
  sourceIndex: number;
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
  width: number; // in timeline pixels
}

export const useDragStateStore = defineStore('dragState', () => {
  const active = ref(false);
  const source = ref<DragState | null>(null);
  const targetIndex = ref(-1);
  const targetTrack = ref(0);
  const ghostTime = ref(0); // calculated drop time in seconds

  const isDragging = computed(() => active.value);

  function startDrag(modId: string, srcIdx: number, clientX: number, clientY: number, cardWidth = 80) {
    active.value = true;
    source.value = {
      moduleId: modId,
      sourceIndex: srcIdx,
      startX: clientX,
      startY: clientY,
      currentX: clientX,
      currentY: clientY,
      width: cardWidth,
    };
    targetIndex.value = srcIdx;
    ghostTime.value = 0;
  }

  function updatePosition(clientX: number, clientY: number) {
    if (!source.value) return;
    source.value.currentX = clientX;
    source.value.currentY = clientY;
  }

  function setTarget(idx: number, track = 0, time = 0) {
    targetIndex.value = idx;
    targetTrack.value = track;
    ghostTime.value = time;
  }

  function endDrag() {
    active.value = false;
    source.value = null;
    targetIndex.value = -1;
  }

  return {
    active, source, targetIndex, targetTrack, ghostTime, isDragging,
    startDrag, updatePosition, setTarget, endDrag,
  };
});
