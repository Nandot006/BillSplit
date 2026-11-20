"use client";

// Receipt photo preparation before upload (design.md §14): accept JPEG, PNG
// and HEIC up to 10 MB, convert HEIC (iPhone photos) to JPEG - the Claude
// API doesn't read HEIC - and shrink to ~2000px on the longest edge so
// storage and the OCR payload stay small.

import { createClient } from "./supabase/client";

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const MAX_EDGE_PX = 2000;
export const BILL_IMAGE_BUCKET = "bill-images";

const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/heic", "image/heif"];
export const ACCEPT_ATTRIBUTE =
  ".jpg,.jpeg,.png,.heic,.heif,image/jpeg,image/png,image/heic,image/heif";

export function isHeic(file: File): boolean {
  return /heic|heif/i.test(file.type) || /\.(heic|heif)$/i.test(file.name);
}

/** Returns a reason the file can't be used, or null if it's fine. */
export function validateReceiptFile(file: File): string | null {
  const typeOk =
    ACCEPTED_TYPES.includes(file.type) || isHeic(file) || /\.(jpe?g|png)$/i.test(file.name);
  if (!typeOk) return "Use a JPEG, PNG or HEIC photo.";
  if (file.size > MAX_UPLOAD_BYTES) return "That photo is over 10 MB. Try a smaller one.";
  return null;
}

/** Longest edge capped at MAX_EDGE_PX, aspect ratio kept. */
export function fitWithin(width: number, height: number, maxEdge = MAX_EDGE_PX) {
  const longest = Math.max(width, height);
  if (longest <= maxEdge) return { width, height };
  const scale = maxEdge / longest;
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

async function toDecodableBlob(file: File): Promise<Blob> {
  if (!isHeic(file)) return file;
  const { default: heic2any } = await import("heic2any");
  const converted = await heic2any({ blob: file, toType: "image/jpeg", quality: 0.9 });
  return Array.isArray(converted) ? converted[0] : converted;
}

/** Converts/resizes the photo and returns a JPEG blob ready to upload. */
export async function prepareReceiptImage(file: File): Promise<Blob> {
  const source = await toDecodableBlob(file);
  const bitmap = await createImageBitmap(source, { imageOrientation: "from-image" });
  const { width, height } = fitWithin(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("This browser can't process images.");
  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", 0.85),
  );
  if (!blob) throw new Error("Couldn't process that photo. Try another one.");
  return blob;
}

/**
 * Uploads to Supabase Storage under the user's own folder - the only place
 * the bucket's access policy lets them write, and the only path the API
 * accepts for a new bill. Returns the storage path.
 */
export async function uploadReceipt(userId: string, image: Blob): Promise<string> {
  const path = `${userId}/${crypto.randomUUID()}.jpg`;
  const supabase = createClient();
  const { error } = await supabase.storage
    .from(BILL_IMAGE_BUCKET)
    .upload(path, image, { contentType: "image/jpeg", upsert: false });
  if (error) throw new Error(`Upload failed: ${error.message}`);
  return path;
}
