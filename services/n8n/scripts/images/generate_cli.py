#!/usr/bin/env python
"""
CLI tool for generating images using Heartsync model.
Removes Gradio UI and provides a simple command-line interface.
"""

from __future__ import annotations

import argparse
import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import requests
import base64
from pathlib import Path
from io import BytesIO
from minio import Minio
from minio.error import S3Error

# Set Hugging Face cache directory to current project folder
os.environ["HF_HOME"] = os.path.join(os.getcwd(), "hf_cache")
os.environ["HF_HUB_CACHE"] = os.path.join(os.getcwd(), "hf_cache")
os.environ["TRANSFORMERS_CACHE"] = os.path.join(os.getcwd(), "hf_cache")


class HeartsyncModel:
    def __init__(self, model_id: str = "Heartsync/NSFW-Uncensored"):
        """Initialize the Heartsync NSFW-Uncensored model."""
        self.model_id = model_id
        self.pipe = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.loaded = False
        
        print(f"Using device: {self.device}")
        
    def load_model(self):
        """Load the model."""
        try:
            print("🔄 Loading model... This may take a few minutes on first run.")
            print("📥 Downloading model components (this only happens once)...")
            
            # Load the pipeline with explicit cache directory
            cache_dir = os.path.join(os.getcwd(), "hf_cache")
            os.makedirs(cache_dir, exist_ok=True)
            
            print("⬇️  Downloading model files... (this may take 5-15 minutes)")
            
            # Enable verbose logging for Hugging Face downloads
            import logging
            logging.getLogger("transformers").setLevel(logging.INFO)
            
            self.pipe = StableDiffusionXLPipeline.from_pretrained(
                self.model_id,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                use_safetensors=True,
                variant="fp16" if self.device == "cuda" else None,
                cache_dir=cache_dir,
                resume_download=True
            )
            
            print("🖥️  Moving model to device...")
            self.pipe = self.pipe.to(self.device)
            
            print("⚡ Enabling memory efficient attention...")
            self.pipe.enable_model_cpu_offload()
            
            print("✅ Model loaded successfully!")
            print("🚀 Ready to generate images!")
            
            self.loaded = True
            return True
            
        except Exception as e:
            error_msg = f"❌ Error loading model: {str(e)}"
            print(error_msg)
            raise
    
    def generate_image(
        self, 
        prompt: str, 
        negative_prompt: str = "",
        num_inference_steps: int = 28,
        guidance_scale: float = 7.5,
        width: int = 1024,
        height: int = 1024,
        seed: Optional[int] = None,
        saturation_boost: float = 1.2,
        contrast_boost: float = 1.1
    ) -> Image.Image:
        """Generate a single image based on the prompt."""
        if not self.loaded or self.pipe is None:
            raise RuntimeError("Model is not loaded. Please load the model first.")
        
        try:
            # Handle seed: if 0 or None, generate a random seed
            if seed is None or seed == 0:
                actual_seed = torch.randint(0, 2**32 - 1, (1,)).item()
            else:
                actual_seed = seed
            
            # Set the seed for reproducible generation
            torch.manual_seed(actual_seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed(actual_seed)
            
            # Generate image
            if self.device == "cuda":
                with torch.autocast(self.device):
                    result = self.pipe(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        num_inference_steps=num_inference_steps,
                        guidance_scale=guidance_scale,
                        width=width,
                        height=height,
                        num_images_per_prompt=1,
                        generator=torch.Generator(device=self.device).manual_seed(actual_seed),
                    )
                    image = result.images[0]
            else:
                result = self.pipe(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    width=width,
                    height=height,
                    num_images_per_prompt=1,
                )
                image = result.images[0]
            
            # Enhance colors and contrast
            image = self.enhance_image_colors(image, saturation_boost, contrast_boost)
            
            return image, actual_seed
            
        except Exception as e:
            raise RuntimeError(f"Error generating image: {str(e)}")
    
    def enhance_image_colors(self, image: Image.Image, saturation_boost: float = 1.2, contrast_boost: float = 1.1) -> Image.Image:
        """Enhance image colors and contrast."""
        from PIL import ImageEnhance
        import numpy as np
        
        # Apply color enhancement
        # 1. Increase saturation
        enhancer = ImageEnhance.Color(image)
        image = enhancer.enhance(saturation_boost)
        
        # 2. Increase contrast
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(contrast_boost)
        
        # 3. Increase brightness slightly
        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(1.05)
        
        # 4. Apply gamma correction for better color distribution
        img_array = np.array(image)
        img_array = np.power(img_array / 255.0, 0.95) * 255.0
        img_array = np.clip(img_array, 0, 255).astype(np.uint8)
        
        return Image.fromarray(img_array)
    
    def save_image_with_metadata(
        self, 
        image: Image.Image, 
        prompt: str, 
        negative_prompt: str,
        num_inference_steps: int,
        guidance_scale: float,
        width: int,
        height: int,
        seed: int,
        saturation_boost: float,
        contrast_boost: float,
        run_id: str,
        output_dir: str,
        minio_client: Optional[Minio] = None,
        minio_bucket: Optional[str] = None,
        minio_public_base: Optional[str] = None
    ) -> Dict[str, str]:
        """Save image and metadata to organized folders and optionally upload to MinIO.
        
        Returns:
            Dict with 'local_path' and optionally 'minio_uri' keys.
        """
        # Create directory structure: {output_dir}/{run_id}/
        save_dir = os.path.join(output_dir, run_id)
        os.makedirs(save_dir, exist_ok=True)
        
        # Generate timestamp in seconds
        timestamp = int(datetime.now().timestamp())
        
        # Save image locally
        image_path = os.path.join(save_dir, f"{timestamp}.png")
        image.save(image_path)
        
        # Prepare image bytes for MinIO upload
        image_bytes = BytesIO()
        image.save(image_bytes, format='PNG')
        image_bytes.seek(0)
        image_data = image_bytes.read()
        
        # Create metadata
        metadata = {
            "timestamp": timestamp,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "seed": seed,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "width": width,
            "height": height,
            "saturation_boost": saturation_boost,
            "contrast_boost": contrast_boost,
            "model_id": self.model_id,
            "run_id": run_id,
            "generated_at": datetime.now().isoformat(),
            "image_path": image_path
        }
        
        # Save metadata as JSON file
        metadata_path_json = os.path.join(save_dir, f"{timestamp}.json")
        with open(metadata_path_json, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        result = {"local_path": image_path}
        
        # Upload to MinIO if configured
        if minio_client and minio_bucket:
            try:
                object_name = f"runs/{run_id}/{timestamp}.png"
                
                # Ensure bucket exists
                if not minio_client.bucket_exists(minio_bucket):
                    minio_client.make_bucket(minio_bucket)
                    print(f"✅ Created MinIO bucket: {minio_bucket}")
                
                # Upload image
                minio_client.put_object(
                    minio_bucket,
                    object_name,
                    BytesIO(image_data),
                    length=len(image_data),
                    content_type="image/png"
                )
                
                # Determine MinIO URI
                if minio_public_base:
                    minio_uri = f"{minio_public_base.rstrip('/')}/{minio_bucket}/{object_name}"
                else:
                    minio_uri = f"s3://{minio_bucket}/{object_name}"
                
                result["minio_uri"] = minio_uri
                metadata["minio_uri"] = minio_uri
                
                # Update metadata file with MinIO URI
                with open(metadata_path_json, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                
                print(f"✅ Image uploaded to MinIO: {minio_uri}")
                
            except S3Error as e:
                print(f"⚠️  Warning: Failed to upload to MinIO: {str(e)}")
            except Exception as e:
                print(f"⚠️  Warning: Error uploading to MinIO: {str(e)}")
        
        return result


def get_minio_client(args: argparse.Namespace) -> Optional[Minio]:
    """Create and return MinIO client if configured."""
    if args.no_minio:
        return None
    
    if not (args.minio_endpoint and args.minio_access_key and args.minio_secret_key):
        return None
    
    try:
        # Remove protocol from endpoint if present
        endpoint = args.minio_endpoint.replace("http://", "").replace("https://", "")
        secure = args.minio_secure or args.minio_endpoint.startswith("https://")
        
        client = Minio(
            endpoint,
            access_key=args.minio_access_key,
            secret_key=args.minio_secret_key,
            secure=secure
        )
        return client
    except Exception as e:
        print(f"⚠️  Warning: Failed to create MinIO client: {str(e)}")
        return None


def post_webhook(webhook_url: str, image_path: str, run_id: str, prompt: str, minio_uri: Optional[str] = None) -> bool:
    """Post webhook notification when image is generated."""
    try:
        payload = {
            "run_id": run_id,
            "image_path": image_path,
            "prompt": prompt,
            "generated_at": datetime.now().isoformat()
        }
        
        if minio_uri:
            payload["minio_uri"] = minio_uri
        
        response = requests.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        print(f"✅ Webhook posted successfully: {image_path}")
        return True
    except Exception as e:
        print(f"⚠️  Warning: Failed to post webhook: {str(e)}")
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate images using Heartsync model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 5 images with tags
  python generate_cli.py --tags "beautiful landscape, detailed" --run-id run123 --num-images 5 --webhook-url http://localhost:8000/webhook
  
  # Generate with custom parameters
  python generate_cli.py --tags "portrait" --run-id run456 --num-images 3 --webhook-url http://localhost:8000/webhook --steps 50 --guidance 8.0
        """
    )
    
    parser.add_argument(
        "--tags",
        required=True,
        help="Comma-separated list of tags/prompt for image generation"
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Run ID to organize generated images in folders"
    )
    parser.add_argument(
        "--num-images",
        type=int,
        default=1,
        help="Number of images to generate (default: 1)"
    )
    parser.add_argument(
        "--webhook-url",
        required=True,
        help="URL to post webhook notification when image is generated"
    )
    parser.add_argument(
        "--output-dir",
        default="./generated-images",
        help="Base output directory for images (default: ./generated-images)"
    )
    parser.add_argument(
        "--negative-prompt",
        default="blurry, low quality, distorted, watermark, text, patreon logo",
        help="Negative prompt (default: 'blurry, low quality, distorted, watermark, text, patreon logo')"
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=28,
        help="Number of inference steps (default: 28)"
    )
    parser.add_argument(
        "--guidance",
        type=float,
        default=7.5,
        help="Guidance scale (default: 7.5)"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1024,
        help="Image width (default: 1024)"
    )
    parser.add_argument(
        "--height",
        type=int,
        default=1024,
        help="Image height (default: 1024)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for generation (default: random)"
    )
    parser.add_argument(
        "--saturation",
        type=float,
        default=1.2,
        help="Saturation boost (default: 1.2)"
    )
    parser.add_argument(
        "--contrast",
        type=float,
        default=1.1,
        help="Contrast boost (default: 1.1)"
    )
    parser.add_argument(
        "--model-id",
        default="Heartsync/NSFW-Uncensored",
        help="Model ID to use (default: Heartsync/NSFW-Uncensored)"
    )
    parser.add_argument(
        "--minio-endpoint",
        default=os.environ.get("MINIO_ENDPOINT", "minio:9000"),
        help="MinIO endpoint (default: minio:9000 or MINIO_ENDPOINT env var)"
    )
    parser.add_argument(
        "--minio-access-key",
        default=os.environ.get("MINIO_ACCESS_KEY", "workflow"),
        help="MinIO access key (default: workflow or MINIO_ACCESS_KEY env var)"
    )
    parser.add_argument(
        "--minio-secret-key",
        default=os.environ.get("MINIO_SECRET_KEY", "workflow_secret"),
        help="MinIO secret key (default: workflow_secret or MINIO_SECRET_KEY env var)"
    )
    parser.add_argument(
        "--minio-bucket",
        default=os.environ.get("MINIO_BUCKET", "runs"),
        help="MinIO bucket name (default: runs or MINIO_BUCKET env var)"
    )
    parser.add_argument(
        "--minio-public-base",
        default=os.environ.get("MINIO_PUBLIC_BASE"),
        help="Optional public base URL for MinIO objects (e.g., http://localhost:9000)"
    )
    parser.add_argument(
        "--minio-secure",
        action="store_true",
        help="Use HTTPS when connecting to MinIO"
    )
    parser.add_argument(
        "--no-minio",
        action="store_true",
        help="Disable MinIO upload even if credentials are provided"
    )
    
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    
    # Parse tags - can be comma-separated or space-separated
    prompt = args.tags.strip()
    
    print(f"🎨 Starting image generation")
    print(f"   Run ID: {args.run_id}")
    print(f"   Prompt: {prompt}")
    print(f"   Number of images: {args.num_images}")
    print(f"   Output directory: {args.output_dir}/{args.run_id}")
    print()
    
    # Initialize MinIO client if configured
    minio_client = get_minio_client(args)
    if minio_client:
        print(f"✅ MinIO client initialized (bucket: {args.minio_bucket})")
    else:
        print("ℹ️  MinIO upload disabled (using local storage only)")
    print()
    
    # Initialize model
    print("Initializing model...")
    model = HeartsyncModel(model_id=args.model_id)
    
    # Load model
    print("Loading model (this may take a while on first run)...")
    model.load_model()
    print()
    
    # Generate images
    generated_paths = []
    base_seed = args.seed if args.seed is not None else None
    
    for i in range(args.num_images):
        print(f"Generating image {i+1}/{args.num_images}...")
        
        # Use different seed for each image if base seed is provided
        current_seed = base_seed + i if base_seed is not None else None
        
        try:
            # Generate image
            image, actual_seed = model.generate_image(
                prompt=prompt,
                negative_prompt=args.negative_prompt,
                num_inference_steps=args.steps,
                guidance_scale=args.guidance,
                width=args.width,
                height=args.height,
                seed=current_seed,
                saturation_boost=args.saturation,
                contrast_boost=args.contrast
            )
            
            # Save image with metadata and upload to MinIO if configured
            save_result = model.save_image_with_metadata(
                image=image,
                prompt=prompt,
                negative_prompt=args.negative_prompt,
                num_inference_steps=args.steps,
                guidance_scale=args.guidance,
                width=args.width,
                height=args.height,
                seed=actual_seed,
                saturation_boost=args.saturation,
                contrast_boost=args.contrast,
                run_id=args.run_id,
                output_dir=args.output_dir,
                minio_client=minio_client,
                minio_bucket=args.minio_bucket if minio_client else None,
                minio_public_base=args.minio_public_base
            )
            
            image_path = save_result["local_path"]
            minio_uri = save_result.get("minio_uri")
            
            generated_paths.append(image_path)
            print(f"✅ Image {i+1} saved: {image_path}")
            if minio_uri:
                print(f"   MinIO URI: {minio_uri}")
            
            # Post webhook
            post_webhook(args.webhook_url, image_path, args.run_id, prompt, minio_uri)
            print()
            
        except Exception as e:
            print(f"❌ Error generating image {i+1}: {str(e)}")
            continue
    
    print(f"🎉 Generation complete!")
    print(f"   Generated {len(generated_paths)}/{args.num_images} images")
    print(f"   All images saved to: {os.path.join(args.output_dir, args.run_id)}")
    
    if len(generated_paths) < args.num_images:
        print(f"⚠️  Warning: Only {len(generated_paths)} out of {args.num_images} images were generated successfully")


if __name__ == "__main__":
    main()

