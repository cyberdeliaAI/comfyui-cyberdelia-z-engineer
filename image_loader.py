"""A compact, Vision-oriented image loader for Prompt Engineer workflows."""

import hashlib
import os
from pathlib import Path


SUPPORTED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
}

VISION_SIZE_OPTIONS = (
    "1536 max (recommended)",
    "1024 max",
    "768 max",
    "512 max",
    "original",
)


def _strip_input_annotation(filename):
    """Return the relative filename used by ComfyUI's input folder."""
    value = str(filename or "").strip()
    suffix = " [input]"
    if value.casefold().endswith(suffix):
        value = value[:-len(suffix)].rstrip()
    return value


def resolve_input_image(input_directory, filename, must_exist=True):
    """Resolve a selected filename while preventing input-directory escapes."""
    root = Path(input_directory).expanduser().resolve()
    relative = _strip_input_annotation(filename)
    if not relative:
        raise ValueError("Select or upload an image first")

    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise ValueError("Only images inside the ComfyUI input folder are allowed")

    candidate = (root / relative_path).resolve()
    try:
        inside_input = os.path.commonpath((str(root), str(candidate))) == str(root)
    except ValueError:
        inside_input = False
    if not inside_input or candidate == root:
        raise ValueError("Only images inside the ComfyUI input folder are allowed")
    if candidate.suffix.casefold() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError("The selected file is not a supported image")
    if must_exist and (not candidate.exists() or not candidate.is_file()):
        raise FileNotFoundError(f"Input image not found: {relative}")
    return candidate


def list_input_images(input_directory):
    """List supported images recursively using ComfyUI-compatible relative paths."""
    root = Path(input_directory).expanduser()
    if not root.exists():
        return []

    images = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in SUPPORTED_IMAGE_EXTENSIONS:
            continue
        try:
            resolved = resolve_input_image(root, path.relative_to(root).as_posix())
        except (OSError, ValueError, FileNotFoundError):
            continue
        images.append(resolved.relative_to(root.resolve()).as_posix())
    return sorted(images, key=str.casefold)


def delete_input_image(input_directory, filename):
    """Delete one explicitly selected input image and return its relative name."""
    root = Path(input_directory).expanduser().resolve()
    path = resolve_input_image(root, filename)
    relative = path.relative_to(root).as_posix()
    path.unlink()
    return relative


def max_dimension_from_option(option):
    """Translate a UI option into a longest-edge limit."""
    value = str(option or "").strip().casefold()
    if value == "original":
        return None
    try:
        dimension = int(value.split()[0])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(f"Unknown Vision size option: {option}") from exc
    if dimension not in {512, 768, 1024, 1536}:
        raise ValueError(f"Unknown Vision size option: {option}")
    return dimension


def resized_dimensions(width, height, max_dimension):
    """Calculate a proportional, downscale-only size."""
    width = int(width)
    height = int(height)
    if width < 1 or height < 1:
        raise ValueError("Image dimensions must be positive")
    if max_dimension is None or max(width, height) <= max_dimension:
        return width, height
    scale = float(max_dimension) / float(max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


class CyberdeliaVisionImageLoader:
    """Load and optionally resize one image for Prompt Engineer Vision mode."""

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths

        images = list_input_images(folder_paths.get_input_directory())
        return {
            "required": {
                "image": (images, {
                    "image_upload": True,
                    "allow_batch": False,
                    "tooltip": "Select or upload one image for Prompt Engineer Vision mode.",
                }),
                "vision_size": (list(VISION_SIZE_OPTIONS), {
                    "default": VISION_SIZE_OPTIONS[0],
                    "tooltip": (
                        "Downscale the longest edge without cropping or upscaling. "
                        "1536 matches Prompt Engineer's internal Vision limit."
                    ),
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "filename")
    FUNCTION = "load_image"
    CATEGORY = "Cyberdelia/Prompt"

    def load_image(self, image, vision_size=VISION_SIZE_OPTIONS[0]):
        import folder_paths
        import numpy as np
        import torch
        from PIL import Image, ImageOps

        path = resolve_input_image(folder_paths.get_input_directory(), image)
        max_dimension = max_dimension_from_option(vision_size)

        try:
            import node_helpers

            opened = node_helpers.pillow(Image.open, path)
        except ImportError:
            opened = Image.open(path)

        with opened as source:
            # Vision requests use the first frame, matching Prompt Engineer's
            # existing first-image behavior for IMAGE batches.
            try:
                source.seek(0)
            except EOFError:
                pass
            loaded = ImageOps.exif_transpose(source).convert("RGB")
            target_size = resized_dimensions(
                loaded.width,
                loaded.height,
                max_dimension,
            )
            if target_size != loaded.size:
                resampling = getattr(Image, "Resampling", Image)
                loaded = loaded.resize(target_size, resampling.LANCZOS)
            array = np.asarray(loaded, dtype=np.float32) / 255.0

        tensor = torch.from_numpy(array)[None,]
        filename = path.relative_to(
            Path(folder_paths.get_input_directory()).expanduser().resolve()
        ).as_posix()
        return tensor, filename

    @classmethod
    def IS_CHANGED(cls, image, vision_size=VISION_SIZE_OPTIONS[0]):
        import folder_paths

        try:
            path = resolve_input_image(folder_paths.get_input_directory(), image)
        except (OSError, ValueError, FileNotFoundError):
            return float("nan")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(str(vision_size).encode("utf-8"))
        return digest.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, image, vision_size=VISION_SIZE_OPTIONS[0]):
        import folder_paths

        try:
            resolve_input_image(folder_paths.get_input_directory(), image)
            max_dimension_from_option(vision_size)
        except (OSError, ValueError, FileNotFoundError) as exc:
            return str(exc)
        return True
