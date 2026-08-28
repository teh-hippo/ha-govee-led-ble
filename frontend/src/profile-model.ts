import type {
  JsonObject,
  MusicProfileContent,
  VideoProfileContent,
} from "./types";
import { cloneRgb } from "./ui-utils";

export type MusicStyleValue = "dynamic" | "calm";
export type VideoCaptureAreaValue = "full" | "part";

export const MUSIC_STYLE_HELP = {
  label: "Style information",
  text: "Dynamic uses the effect's more active response.  Calm uses a more restrained response.",
} as const;

export function musicStyleValue(calm: boolean | null): MusicStyleValue {
  return calm === true ? "calm" : "dynamic";
}

export function musicStyleCalm(value: string): boolean {
  return value === "calm";
}

export function videoCaptureAreaValue(
  fullScreen: boolean,
): VideoCaptureAreaValue {
  return fullScreen ? "full" : "part";
}

export function videoCaptureAreaFullScreen(value: string): boolean {
  return value === "full";
}

export function cloneVideoProfileContent(
  content: VideoProfileContent,
): VideoProfileContent {
  return {
    ...content,
    relative_brightness: { ...content.relative_brightness },
  };
}

export function cloneMusicProfileContent(
  content: MusicProfileContent,
): MusicProfileContent {
  return {
    ...content,
    colour: content.colour === null ? null : cloneRgb(content.colour),
    parameters: cloneJsonObject(content.parameters),
  };
}

export function cloneJsonObject(value: JsonObject): JsonObject {
  return structuredClone(value) as JsonObject;
}
