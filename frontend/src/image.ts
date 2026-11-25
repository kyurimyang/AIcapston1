// 전송 전 리사이즈. 폰 원본(수 MB)을 그대로 보내면 ngrok 업로드만으로 3초 목표를 넘긴다.
// CLIP 입력은 224px이라 긴 변 768px이면 인식 정확도에 영향이 없다.
const MAX_SIDE = 768;
const QUALITY = 0.85;

function toJpeg(src: CanvasImageSource, w: number, h: number): Promise<Blob> {
  const scale = Math.min(1, MAX_SIDE / Math.max(w, h));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  canvas.getContext("2d")!.drawImage(src, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("이미지 변환 실패"))), "image/jpeg", QUALITY),
  );
}

/** 카메라 미리보기의 현재 프레임을 찍는다. */
export function captureFrame(video: HTMLVideoElement): Promise<Blob> {
  return toJpeg(video, video.videoWidth, video.videoHeight);
}

/** 첨부한 영상에서 가운데 장면 한 장을 뽑는다. */
export function frameFromVideoFile(file: Blob): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const v = document.createElement("video");
    v.muted = true;
    v.playsInline = true;
    v.preload = "auto";
    const done = () => URL.revokeObjectURL(url);
    v.onloadedmetadata = () => { v.currentTime = Number.isFinite(v.duration) ? v.duration / 2 : 0; };
    v.onseeked = () => toJpeg(v, v.videoWidth, v.videoHeight).then(resolve, reject).finally(done);
    v.onerror = () => { done(); reject(new Error("영상을 열 수 없어요")); };
    v.src = url;
  });
}

/** 첨부한 파일(사진 또는 영상)을 인식용 JPEG로 바꾼다. */
export function fromFile(file: File): Promise<Blob> {
  return file.type.startsWith("video/") ? frameFromVideoFile(file) : resizeFile(file);
}

/** 업로드한 사진을 줄인다. canvas는 EXIF를 버리므로 회전을 먼저 반영한다. */
export async function resizeFile(file: Blob): Promise<Blob> {
  const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
  try {
    return await toJpeg(bmp, bmp.width, bmp.height);
  } finally {
    bmp.close();
  }
}
