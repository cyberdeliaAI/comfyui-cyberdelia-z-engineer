"""Convert ComfyUI images into OpenAI-compatible vision message content."""

import base64
from io import BytesIO


VISION_MAX_DIMENSION = 1536
DEFAULT_VISION_INSTRUCTION = (
    "Analyze the attached image and convert its visible content into a detailed "
    "image-generation prompt. Treat the image as the primary reference. Preserve "
    "the subject, composition, pose, clothing, environment, lighting, colors, "
    "textures, camera perspective, depth of field, and mood. Return only the final "
    "prompt."
)


def image_to_data_url(image, max_dimension=VISION_MAX_DIMENSION):
    """Encode the first ComfyUI IMAGE batch item as a local base64 data URL."""
    from PIL import Image

    ndim = int(getattr(image, "ndim", 0))
    if ndim == 4:
        frame = image[0]
    elif ndim == 3:
        frame = image
    else:
        raise ValueError("Vision input must be a ComfyUI IMAGE tensor [B,H,W,C]")

    frame = frame.detach().cpu().clamp(0.0, 1.0)
    array = (frame * 255.0).round().byte().numpy()
    if array.ndim != 3 or array.shape[-1] not in {1, 3, 4}:
        raise ValueError("Vision input must contain 1, 3, or 4 image channels")
    if array.shape[-1] == 1:
        array = array[:, :, 0]

    pil_image = Image.fromarray(array)
    if max(pil_image.size) > max_dimension:
        resampling = getattr(Image, "Resampling", Image)
        pil_image.thumbnail((max_dimension, max_dimension), resampling.LANCZOS)

    buffer = BytesIO()
    if pil_image.mode in {"RGBA", "LA"}:
        mime_type = "image/png"
        pil_image.save(buffer, format="PNG", optimize=True)
    else:
        mime_type = "image/jpeg"
        pil_image.convert("RGB").save(
            buffer,
            format="JPEG",
            quality=90,
            optimize=True,
        )

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_vision_user_content(text, image_data_url):
    """Build a Chat Completions multimodal user message."""
    user_direction = str(text or "").strip()
    instruction = DEFAULT_VISION_INSTRUCTION
    if user_direction:
        instruction += f"\n\nAdditional direction from the user:\n{user_direction}"
    return [
        {"type": "text", "text": instruction},
        {
            "type": "image_url",
            "image_url": {
                "url": image_data_url,
                "detail": "auto",
            },
        },
    ]
