import { defineStore } from 'pinia';
import { ref } from 'vue';

export const usePlaybackStore = defineStore('playback', () => {
  const isPlaying = ref(false);
  const currentTime = ref(0);
  const zoomLevel = ref(1.0);

  function play() { isPlaying.value = true; }
  function pause() { isPlaying.value = false; }
  function seekTo(time: number) { currentTime.value = Math.max(0, time); }
  function setZoom(level: number) { zoomLevel.value = Math.max(0.1, Math.min(5.0, level)); }

  return { isPlaying, currentTime, zoomLevel, play, pause, seekTo, setZoom };
});
