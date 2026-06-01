/** TypeScript type definitions for the Migratable Script format.
 *  Mirrors the Pydantic models in backend/models/script.py and
 *  the JSON Schema in script/schema.py.
 */

/** Source material types */
export type SourceType = 'video' | 'image' | 'text' | 'audio' | 'effect';

/** Module type enumeration */
export type ModuleType =
  | 'title'
  | 'video_segment'
  | 'subtitle'
  | 'transition'
  | 'audio'
  | 'effect';

/** Track type enumeration */
export type TrackType = 'video' | 'audio' | 'text' | 'effect';

/** Structure type from narrative inference (matches understand/structure.py) */
export type StructureType =
  | 'opening'
  | 'highlight'
  | 'transition'
  | 'effect'
  | 'closing'
  | 'unclassified';

/** Reference to a source asset file */
export interface SourceMaterial {
  type: SourceType;
  path: string;
  start_offset: number;
  end_offset: number;
}

/** Position on the canvas */
export interface Position {
  x: number;
  y: number;
}

/** Renderer-agnostic module parameters */
export interface ModuleParams {
  text_content?: string;
  font_size?: number;
  font_color?: string;
  position?: Position;
  animation?: string;
  volume?: number;  // 0.0 - 1.0
  transition_type?: string;
}

/** A single module on the timeline */
export interface Module {
  id: string;
  type: ModuleType;
  label?: string;
  start_time: number;
  duration: number;
  track_index: number;
  source?: SourceMaterial;
  params?: ModuleParams;
  children: Module[];
  detail?: Record<string, any>;
}

/** A timeline track definition */
export interface Track {
  index: number;
  name: string;
  type: TrackType;
  muted: boolean;
  locked: boolean;
}

/** Video resolution */
export interface Resolution {
  width: number;
  height: number;
}

/** Project metadata */
export interface Metadata {
  title: string;
  description: string;
  author: string;
  created_at: string;  // ISO 8601
  total_duration: number;
  source_video_id: string;
  fps: number;
  resolution: Resolution;
  tags: string[];
}

/** Complete MigratableScript */
export interface MigratableScript {
  version: string;
  metadata: Metadata;
  modules: Module[];
  tracks: Track[];
}

/** Narrative structure segment */
export interface StructureSegment {
  start_time: number;
  end_time: number;
  structure_type: StructureType;
  confidence: number;
  evidence: string[];
}

/** Analysis result from the backend */
export interface AnalysisResult {
  video_id: string;
  status: 'processing' | 'completed' | 'failed';
  script?: MigratableScript;
  error?: string;
}

/** Upload response */
export interface UploadResult {
  video_id: string;
  filename: string;
  size_bytes: number;
  duration?: number;
  width?: number;
  height?: number;
  fps?: number;
}

/** Export response */
export interface ExportResult {
  video_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  output_path?: string;
  error?: string;
}

/** Drag and drop payload for timeline reordering */
export interface DragPayload {
  moduleId: string;
  fromTrackIndex: number;
  fromIndex: number;
}

/** Drop target info */
export interface DropTarget {
  trackIndex: number;
  insertIndex: number;
}
