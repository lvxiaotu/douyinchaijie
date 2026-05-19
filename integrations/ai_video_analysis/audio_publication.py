from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


@dataclass
class PublishedAudio:
    url: str
    path: str = ""
    relative_path: str = ""
    mode: str = ""
    storage_key: str = ""
    expires_in_seconds: int = 0


def configured_public_dir() -> Path:
    configured = os.getenv("AI_VIDEO_ASR_PUBLIC_DIR") or ""
    if configured:
        return Path(configured)
    output_dir = Path(os.getenv("AI_VIDEO_OUTPUT_DIR") or "data/runtime/ai_video_analysis")
    return output_dir / "public_asr_audio"


def configured_public_base_url() -> str:
    return os.getenv("AI_VIDEO_ASR_PUBLIC_BASE_URL") or os.getenv("AI_VIDEO_PUBLIC_BASE_URL") or ""


def configured_publisher_mode() -> str:
    configured = (os.getenv("AI_VIDEO_ASR_PUBLISHER") or os.getenv("AI_VIDEO_ASR_PUBLICATION_MODE") or "").lower()
    if configured:
        return configured
    if os.getenv("VOLCENGINE_TOS_BUCKET") or os.getenv("TOS_BUCKET"):
        return "tos"
    return "local"


def tos_config_status() -> dict[str, bool]:
    return {
        "access_key_configured": bool(os.getenv("VOLCENGINE_TOS_ACCESS_KEY") or os.getenv("TOS_ACCESS_KEY") or os.getenv("TOS_AK")),
        "secret_key_configured": bool(os.getenv("VOLCENGINE_TOS_SECRET_KEY") or os.getenv("TOS_SECRET_KEY") or os.getenv("TOS_SK")),
        "endpoint_configured": bool(os.getenv("VOLCENGINE_TOS_ENDPOINT") or os.getenv("TOS_ENDPOINT")),
        "region_configured": bool(os.getenv("VOLCENGINE_TOS_REGION") or os.getenv("TOS_REGION")),
        "bucket_configured": bool(os.getenv("VOLCENGINE_TOS_BUCKET") or os.getenv("TOS_BUCKET")),
    }


class AudioPublisher:
    """Publish local ASR audio files for third-party ASR pull access."""

    def __init__(
        self,
        *,
        public_dir: Path | None = None,
        public_base_url: str | None = None,
    ):
        self.public_dir = Path(public_dir) if public_dir else configured_public_dir()
        self.public_base_url = public_base_url if public_base_url is not None else configured_public_base_url()

    def resolve_or_publish(self, audio_path: Path) -> PublishedAudio | None:
        explicit_url = os.getenv("AI_VIDEO_ASR_AUDIO_URL") or os.getenv("VOLCENGINE_ASR_AUDIO_URL") or ""
        if explicit_url:
            return PublishedAudio(url=explicit_url, mode="explicit")

        mode = configured_publisher_mode()
        if mode in {"tos", "volcengine_tos", "object_storage", "oss"}:
            return TosAudioPublisher().publish(audio_path)

        mapped = self.resolve_existing_public_url(audio_path)
        if mapped:
            return mapped

        if not self.public_base_url:
            return None
        return self.publish(audio_path)

    def resolve_existing_public_url(self, audio_path: Path) -> PublishedAudio | None:
        public_root = os.getenv("AI_VIDEO_ASR_PUBLIC_ROOT") or ""
        base_url = self.public_base_url
        if not public_root or not base_url:
            return None
        try:
            relative = audio_path.resolve().relative_to(Path(public_root).resolve())
        except ValueError:
            return None
        return PublishedAudio(
            url=self.join_url(base_url, relative.as_posix()),
            path=str(audio_path),
            relative_path=relative.as_posix(),
            mode="mapped",
        )

    def publish(self, audio_path: Path) -> PublishedAudio:
        if not audio_path.exists() or not audio_path.is_file():
            raise RuntimeError(f"ASR audio file does not exist: {audio_path}")
        digest = self.audio_digest(audio_path)
        job_id = self.safe_segment(audio_path.parent.name or "audio")
        suffix = audio_path.suffix.lower() if audio_path.suffix else ".wav"
        relative = Path(job_id) / f"{digest}{suffix}"
        target = self.public_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.stat().st_size != audio_path.stat().st_size:
            shutil.copy2(audio_path, target)
        return PublishedAudio(
            url=self.join_url(self.public_base_url, relative.as_posix()),
            path=str(target),
            relative_path=relative.as_posix(),
            mode="copied",
        )

    def audio_digest(self, audio_path: Path) -> str:
        salt = os.getenv("AI_VIDEO_ASR_PUBLIC_TOKEN_SALT") or ""
        digest = hashlib.sha256()
        if salt:
            digest.update(salt.encode("utf-8"))
        with audio_path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()[:24]

    def join_url(self, base_url: str, relative_path: str) -> str:
        encoded = "/".join(quote(part) for part in relative_path.replace("\\", "/").split("/") if part)
        return f"{base_url.rstrip('/')}/{encoded}"

    def safe_segment(self, value: str) -> str:
        safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
        return safe[:80] or "audio"


class TosAudioPublisher:
    """Publish audio to Volcengine TOS and return a public or pre-signed URL."""

    def __init__(
        self,
        *,
        ak: str | None = None,
        sk: str | None = None,
        endpoint: str | None = None,
        region: str | None = None,
        bucket: str | None = None,
        prefix: str | None = None,
        public_base_url: str | None = None,
        use_presigned_url: bool | None = None,
        presign_expires_seconds: int | None = None,
        tos_module: object | None = None,
        client: object | None = None,
    ):
        self.ak = ak or os.getenv("VOLCENGINE_TOS_ACCESS_KEY") or os.getenv("TOS_ACCESS_KEY") or os.getenv("TOS_AK") or ""
        self.sk = sk or os.getenv("VOLCENGINE_TOS_SECRET_KEY") or os.getenv("TOS_SECRET_KEY") or os.getenv("TOS_SK") or ""
        self.endpoint = endpoint or os.getenv("VOLCENGINE_TOS_ENDPOINT") or os.getenv("TOS_ENDPOINT") or ""
        self.region = region or os.getenv("VOLCENGINE_TOS_REGION") or os.getenv("TOS_REGION") or ""
        self.bucket = bucket or os.getenv("VOLCENGINE_TOS_BUCKET") or os.getenv("TOS_BUCKET") or ""
        self.prefix = (prefix if prefix is not None else os.getenv("VOLCENGINE_TOS_PREFIX") or os.getenv("TOS_PREFIX") or "ai-video-asr/audio").strip("/")
        self.public_base_url = public_base_url if public_base_url is not None else os.getenv("VOLCENGINE_TOS_PUBLIC_BASE_URL") or os.getenv("TOS_PUBLIC_BASE_URL") or ""
        if use_presigned_url is None:
            use_presigned_url = (os.getenv("VOLCENGINE_TOS_USE_PRESIGNED_URL", "true").lower() not in {"0", "false", "no"})
        self.use_presigned_url = use_presigned_url
        self.presign_expires_seconds = int(
            presign_expires_seconds
            if presign_expires_seconds is not None
            else os.getenv("VOLCENGINE_TOS_PRESIGN_EXPIRES_SECONDS", "86400")
            or 86400
        )
        self.tos_module = tos_module
        self.client = client

    def publish(self, audio_path: Path) -> PublishedAudio:
        self.validate()
        if not audio_path.exists() or not audio_path.is_file():
            raise RuntimeError(f"ASR audio file does not exist: {audio_path}")
        client = self.client or self.create_client()
        object_key = self.object_key(audio_path)
        self.upload_file(client, audio_path, object_key)
        url = self.object_url(client, object_key)
        return PublishedAudio(
            url=url,
            path=str(audio_path),
            relative_path=object_key,
            storage_key=object_key,
            mode="tos_presigned" if self.use_presigned_url else "tos_public",
            expires_in_seconds=self.presign_expires_seconds if self.use_presigned_url else 0,
        )

    def validate(self) -> None:
        missing = []
        for name, value in [
            ("VOLCENGINE_TOS_ACCESS_KEY", self.ak),
            ("VOLCENGINE_TOS_SECRET_KEY", self.sk),
            ("VOLCENGINE_TOS_ENDPOINT", self.endpoint),
            ("VOLCENGINE_TOS_REGION", self.region),
            ("VOLCENGINE_TOS_BUCKET", self.bucket),
        ]:
            if not value:
                missing.append(name)
        if missing:
            raise RuntimeError(f"Missing Volcengine TOS config: {', '.join(missing)}")

    def create_client(self):
        tos = self.tos_module or self.import_tos()
        return tos.TosClientV2(self.ak, self.sk, self.endpoint, self.region)

    def import_tos(self):
        try:
            import tos  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Missing Volcengine TOS Python SDK. Install it with: pip install tos") from exc
        self.tos_module = tos
        return tos

    def object_key(self, audio_path: Path) -> str:
        digest = AudioPublisher().audio_digest(audio_path)
        job_id = AudioPublisher().safe_segment(audio_path.parent.name or "audio")
        suffix = audio_path.suffix.lower() if audio_path.suffix else ".wav"
        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        parts = [part for part in [self.prefix, date_prefix, job_id, f"{digest}{suffix}"] if part]
        return "/".join(parts)

    def upload_file(self, client: object, audio_path: Path, object_key: str) -> None:
        content_type = mimetypes.guess_type(audio_path.name)[0] or "audio/wav"
        if hasattr(client, "put_object_from_file"):
            try:
                client.put_object_from_file(self.bucket, object_key, str(audio_path), content_type=content_type)
                return
            except TypeError:
                client.put_object_from_file(self.bucket, object_key, str(audio_path))
                return
        if hasattr(client, "upload_file"):
            client.upload_file(self.bucket, object_key, str(audio_path), task_num=int(os.getenv("VOLCENGINE_TOS_UPLOAD_TASK_NUM", "3") or 3))
            return
        if hasattr(client, "put_object"):
            with audio_path.open("rb") as file:
                client.put_object(self.bucket, object_key, content=file, content_type=content_type)
            return
        raise RuntimeError("Configured TOS client does not support file upload.")

    def object_url(self, client: object, object_key: str) -> str:
        if self.use_presigned_url:
            tos = self.tos_module or self.import_tos()
            http_get = tos.HttpMethodType.Http_Method_Get
            try:
                result = client.pre_signed_url(
                    http_method=http_get,
                    bucket=self.bucket,
                    key=object_key,
                    expires=self.presign_expires_seconds,
                )
            except TypeError:
                result = client.pre_signed_url(http_get, bucket=self.bucket, key=object_key, expires=self.presign_expires_seconds)
            return str(getattr(result, "signed_url", result))
        if not self.public_base_url:
            return f"https://{self.bucket}.{self.endpoint}/{AudioPublisher().join_url('', object_key).lstrip('/')}"
        return AudioPublisher().join_url(self.public_base_url, object_key)
