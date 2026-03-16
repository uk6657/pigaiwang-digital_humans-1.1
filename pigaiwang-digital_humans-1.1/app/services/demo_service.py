"""Core services for the digital human demo APIs."""

from __future__ import annotations

import mimetypes
import shutil
import subprocess
from asyncio import to_thread
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select, update

from app.configs import base_configs
from app.storage import (
    AsyncSessionLocal,
    GroupModel,
    GroupVideoConfigModel,
    UserModel,
    VideoModel,
    VideoPlaybackType,
    VideoProcessStatus,
    VideoSourceType,
    VideoSyncStatus,
)


class DemoService:
    """Business logic for groups, videos, and saved group sequences."""

    FIXED_GROUPS: tuple[tuple[int, int, str], ...] = (
        (1001, 1, "第一组"),
        (1002, 2, "第二组"),
        (1003, 3, "第三组"),
        (1004, 4, "第四组"),
    )
    def __init__(self) -> None:
        self.media_dir = Path(base_configs.PROJECT_DIR) / "media"
        self.upload_dir = self.media_dir / "uploads"
        self.hls_root = Path(base_configs.PROJECT_DATA_DIR) / "hls" / "videos"

    def serialize_video(self, video: VideoModel) -> dict:
        """Convert a video ORM object into a plain response-safe dict."""

        stream_url = self.get_stream_url(video.id)
        hls_url = self.get_hls_manifest_url(video.id)
        use_hls = self.get_hls_manifest_path(video.id).exists()
        has_playable_file = bool(video.is_available and video.file_path)
        return {
            "id": video.id,
            "group_id": video.group_id,
            "external_video_id": video.external_video_id,
            "video_name": video.video_name,
            "description": video.description,
            "file_name": video.file_name,
            "file_path": video.file_path,
            "access_url": (
                hls_url if use_hls else stream_url
            ) if has_playable_file else None,
            "source_type": video.source_type,
            "stream_url": stream_url if has_playable_file else None,
            "hls_url": hls_url if use_hls and has_playable_file else None,
            "playback_type": video.playback_type,
            "process_status": video.process_status,
            "duration_seconds": video.duration_seconds,
            "file_size_bytes": video.file_size_bytes,
            "mime_type": video.mime_type,
            "is_available": video.is_available,
            "created_at": video.created_at,
            "updated_at": video.updated_at,
        }

    @staticmethod
    def build_virtual_file_path(external_video_id: str) -> str:
        """Build a stable unique placeholder path for videos without local files."""

        return f"virtual://{external_video_id}"

    @staticmethod
    def sanitize_file_token(value: str) -> str:
        """Build a filesystem-safe token for saved upload file names."""

        cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
        return cleaned.strip("_") or "video"

    async def bootstrap(self) -> None:
        """Ensure fixed groups and group configs exist."""

        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.hls_root.mkdir(parents=True, exist_ok=True)
        await self.ensure_groups()
        await self.ensure_group_configs()

    async def ensure_groups(self) -> None:
        """Ensure the four fixed demo groups exist with fixed IDs."""

        async with AsyncSessionLocal() as session:
            changed = False
            groups = (await session.execute(select(GroupModel))).scalars().all()
            existing_by_id = {item.id: item for item in groups}
            existing_by_no = {item.group_no: item for item in groups}

            for group_id, group_no, group_name in self.FIXED_GROUPS:
                group = existing_by_id.get(group_id)
                legacy_group = None
                if group is None:
                    legacy_group = existing_by_no.get(group_no)
                if group is None and legacy_group is None:
                    session.add(
                        GroupModel(
                            id=group_id,
                            group_no=group_no,
                            group_name=group_name,
                            description=group_name,
                            is_active=True,
                        )
                    )
                    changed = True
                    continue

                if group is None and legacy_group is not None:
                    group = GroupModel(
                        id=group_id,
                        group_no=group_no,
                        group_name=group_name,
                        description=group_name,
                        is_active=True,
                    )
                    session.add(group)
                    await session.flush()

                    await session.execute(
                        update(VideoModel)
                        .where(VideoModel.group_id == legacy_group.id)
                        .values(group_id=group_id)
                    )
                    await session.execute(
                        update(GroupVideoConfigModel)
                        .where(GroupVideoConfigModel.group_id == legacy_group.id)
                        .values(group_id=group_id)
                    )

                    legacy_group.group_no = 10000 + group_no
                    legacy_group.group_name = f"legacy-{group_name}"
                    legacy_group.description = "legacy migrated group"
                    legacy_group.is_active = False
                    legacy_group.is_deleted = True
                    changed = True

                if (
                    not group.is_active
                    or group.group_no != group_no
                    or group.group_name != group_name
                    or group.description != group_name
                ):
                    group.is_active = True
                    group.group_no = group_no
                    group.group_name = group_name
                    group.description = group_name
                    changed = True

            if changed:
                await session.commit()

    async def sync_local_videos(self) -> None:
        """Scan local media files and keep video metadata in sync."""

        async with AsyncSessionLocal() as session:
            videos = (
                await session.execute(
                    select(VideoModel).where(VideoModel.is_deleted == False)  # noqa: E712
                )
            ).scalars().all()
            videos_by_path = {item.file_path: item for item in videos}
            disk_files = list(self.media_dir.glob("*.mp4"))
            disk_paths = {str(path.resolve()) for path in disk_files}
            changed = False

            for video in videos:
                if video.file_path and video.file_path not in disk_paths:
                    video.is_available = False
                    video.sync_status = VideoSyncStatus.missing.value
                    changed = True

            for path in disk_files:
                resolved_path = str(path.resolve())
                stat = path.stat()
                video_name = path.stem
                mime_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
                source_type = self.detect_source_type(path.name)

                video = videos_by_path.get(resolved_path)
                if video is None:
                    stmt = select(VideoModel).where(
                        VideoModel.file_path == resolved_path,
                    )
                    video = (await session.execute(stmt)).scalar_one_or_none()
                    if video is not None:
                        video.is_deleted = False
                        videos_by_path[resolved_path] = video

                if video is None:
                    stmt = select(VideoModel).where(
                        VideoModel.external_video_id == path.stem,
                    )
                    video = (await session.execute(stmt)).scalar_one_or_none()
                    if video is not None:
                        video.is_deleted = False
                        video.file_path = resolved_path
                        video.file_name = path.name
                        videos_by_path[resolved_path] = video

                if video is None:
                    video = VideoModel(
                        group_id=None,
                        external_video_id=path.stem,
                        video_name=video_name,
                        description=None,
                        file_name=path.name,
                        file_path=resolved_path,
                        access_url="",
                        source_type=source_type,
                        playback_type=VideoPlaybackType.mp4.value,
                        process_status=VideoProcessStatus.uploaded.value,
                        duration_seconds=None,
                        file_size_bytes=stat.st_size,
                        mime_type=mime_type,
                        sync_status=VideoSyncStatus.synced.value,
                        is_available=True,
                    )
                    session.add(video)
                    await session.flush()
                else:
                    video.is_deleted = False
                    video.external_video_id = video.external_video_id or path.stem
                    video.video_name = video_name
                    video.file_name = path.name
                    video.file_path = resolved_path
                    video.source_type = source_type
                    video.file_size_bytes = stat.st_size
                    video.mime_type = mime_type
                    video.is_available = True
                    video.sync_status = VideoSyncStatus.synced.value

                await self.ensure_hls_assets(video.id, path)
                video.playback_type = self.detect_playback_type(video.id)
                video.process_status = self.detect_process_status(video.id)
                video.access_url = self.get_default_playback_url(video.id)
                changed = True

            if changed:
                await session.commit()

    async def ensure_group_configs(self) -> None:
        """Ensure each fixed group has an empty config row by default."""

        async with AsyncSessionLocal() as session:
            groups = (
                await session.execute(
                    select(GroupModel).where(
                        GroupModel.id.in_([item[0] for item in self.FIXED_GROUPS])  # type: ignore[arg-type]
                    )
                )
            ).scalars().all()
            existing = {
                item.group_id: item
                for item in (
                    await session.execute(select(GroupVideoConfigModel))
                ).scalars().all()
            }

            changed = False
            for group in groups:
                if group.id not in existing:
                    session.add(
                        GroupVideoConfigModel(
                            group_id=group.id,
                            video_ids=[],
                            version=1,
                        )
                    )
                    changed = True

            if changed:
                await session.commit()

    async def get_current_user(self, user_id: int) -> UserModel:
        """Fetch current user by id."""

        async with AsyncSessionLocal() as session:
            stmt = select(UserModel).where(
                UserModel.id == user_id,
                UserModel.is_deleted == False,  # noqa: E712
            )
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user is None:
                raise HTTPException(status_code=404, detail="User not found")
            return user

    async def list_groups(self) -> list[GroupModel]:
        """Return the fixed active groups."""

        await self.bootstrap()
        async with AsyncSessionLocal() as session:
            stmt = (
                select(GroupModel)
                .where(
                    GroupModel.id.in_([item[0] for item in self.FIXED_GROUPS]),  # type: ignore[arg-type]
                    GroupModel.is_deleted == False,  # noqa: E712
                    GroupModel.is_active == True,  # noqa: E712
                )
                .order_by(GroupModel.id.asc())
            )
            return list((await session.execute(stmt)).scalars().all())

    async def list_videos(self, group_id: int | None = None) -> list[VideoModel]:
        """Return all videos, or the ordered configured videos for one group."""

        await self.bootstrap()
        async with AsyncSessionLocal() as session:
            stmt = (
                select(VideoModel)
                .where(
                    VideoModel.is_deleted == False,  # noqa: E712
                    VideoModel.is_available == True,  # noqa: E712
                )
                .order_by(VideoModel.id.asc())
            )
            if group_id is None:
                return list((await session.execute(stmt)).scalars().all())

            await self._require_group(session, group_id)
            config_stmt = select(GroupVideoConfigModel).where(
                GroupVideoConfigModel.group_id == group_id
            )
            config = (await session.execute(config_stmt)).scalar_one_or_none()
            if config is None or not config.video_ids:
                return []

            stmt = stmt.where(VideoModel.id.in_(config.video_ids))  # type: ignore[arg-type]
            videos = list((await session.execute(stmt)).scalars().all())
            video_map = {video.id: video for video in videos}
            return [video_map[video_id] for video_id in config.video_ids if video_id in video_map]

    async def get_video_detail(self, video_id: int) -> VideoModel:
        """Fetch a single video row."""

        await self.bootstrap()
        async with AsyncSessionLocal() as session:
            stmt = select(VideoModel).where(
                VideoModel.id == video_id,
                VideoModel.is_deleted == False,  # noqa: E712
            )
            result = await session.execute(stmt)
            video = result.scalar_one_or_none()
            if video is None:
                raise HTTPException(status_code=404, detail="Video not found")
            return video

    async def list_cache_manifest(self) -> list[dict]:
        """Return all downloadable videos for local cache clients."""

        await self.bootstrap()
        async with AsyncSessionLocal() as session:
            stmt = (
                select(VideoModel)
                .where(
                    VideoModel.is_deleted == False,  # noqa: E712
                    VideoModel.is_available == True,  # noqa: E712
                )
                .order_by(VideoModel.id.asc())
            )
            videos = (await session.execute(stmt)).scalars().all()
            videos = [video for video in videos if self.is_real_uploaded_video(video)]
            return [
                {
                    "video_id": video.id,
                    "external_video_id": video.external_video_id,
                    "video_name": video.video_name,
                    "file_name": video.file_name,
                    "file_size_bytes": video.file_size_bytes,
                    "mime_type": video.mime_type,
                    "updated_at": video.updated_at,
                    "download_url": self.get_download_url(video.id),
                }
                for video in videos
            ]

    @staticmethod
    def is_real_uploaded_video(video: VideoModel) -> bool:
        """Return whether a video points to a real uploaded local file."""

        if not video.is_available or not video.file_path:
            return False
        if str(video.file_path).startswith("virtual://"):
            return False
        return Path(video.file_path).exists()

    async def list_downloadable_manifest(self) -> list[dict]:
        """Return only videos that are truly downloadable from local storage."""

        await self.bootstrap()
        async with AsyncSessionLocal() as session:
            stmt = (
                select(VideoModel)
                .where(
                    VideoModel.is_deleted == False,  # noqa: E712
                    VideoModel.is_available == True,  # noqa: E712
                )
                .order_by(VideoModel.id.asc())
            )
            videos = (await session.execute(stmt)).scalars().all()
            downloadable_videos = [
                video for video in videos if self.is_real_uploaded_video(video)
            ]
            return [
                {
                    "video_id": video.id,
                    "external_video_id": video.external_video_id,
                    "video_name": video.video_name,
                    "file_name": video.file_name,
                    "file_size_bytes": video.file_size_bytes,
                    "mime_type": video.mime_type,
                    "updated_at": video.updated_at,
                    "download_url": self.get_download_url(video.id),
                }
                for video in downloadable_videos
            ]

    async def list_cache_versions(self) -> list[dict]:
        """Return compact cache version information for all downloadable videos."""

        await self.bootstrap()
        async with AsyncSessionLocal() as session:
            stmt = (
                select(VideoModel)
                .where(
                    VideoModel.is_deleted == False,  # noqa: E712
                    VideoModel.is_available == True,  # noqa: E712
                )
                .order_by(VideoModel.id.asc())
            )
            videos = (await session.execute(stmt)).scalars().all()
            videos = [video for video in videos if self.is_real_uploaded_video(video)]
            return [
                {
                    "video_id": video.id,
                    "updated_at": video.updated_at,
                    "file_size_bytes": video.file_size_bytes,
                }
                for video in videos
            ]

    async def download_video_file(self, video_id: int) -> FileResponse:
        """Return the original uploaded video file as a direct download."""

        file_path = await self.get_video_path(video_id)
        media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=file_path.name,
        )

    async def get_group_video_config(self, group_id: int) -> dict:
        """Return saved group configuration and ordered video details."""

        await self.bootstrap()
        async with AsyncSessionLocal() as session:
            await self._require_group(session, group_id)
            stmt = select(GroupVideoConfigModel).where(GroupVideoConfigModel.group_id == group_id)
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()
            if config is None:
                config = GroupVideoConfigModel(group_id=group_id, video_ids=[], version=1)
                session.add(config)
                await session.commit()
                config_video_ids: list[int] = []
            else:
                config_video_ids = list(config.video_ids)

            ordered_videos: list[dict] = []
            if config_video_ids:
                video_stmt = select(VideoModel).where(
                    VideoModel.id.in_(config_video_ids),  # type: ignore[arg-type]
                    VideoModel.is_deleted == False,  # noqa: E712
                )
                fetched = (await session.execute(video_stmt)).scalars().all()
                video_map = {video.id: video for video in fetched}
                ordered_videos = [
                    self.serialize_video(video_map[video_id])
                    for video_id in config_video_ids
                    if video_id in video_map
                ]

            return {
                "group_id": group_id,
                "video_ids": config_video_ids,
                "videos": ordered_videos,
            }

    async def save_group_video_config(
        self,
        group_id: int,
        video_ids: list[int],
        updated_by: int | None = None,
    ) -> dict:
        """Persist the ordered video ids for a group."""

        await self.bootstrap()
        async with AsyncSessionLocal() as session:
            await self._require_group(session, group_id)
            videos: list[VideoModel] = []
            if video_ids:
                stmt = select(VideoModel).where(
                    VideoModel.id.in_(set(video_ids)),  # type: ignore[arg-type]
                    VideoModel.is_deleted == False,  # noqa: E712
                )
                videos = list((await session.execute(stmt)).scalars().all())
                if len(videos) != len(set(video_ids)):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Some video ids do not exist",
                    )

            stmt = select(GroupVideoConfigModel).where(GroupVideoConfigModel.group_id == group_id)
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()
            if config is None:
                config = GroupVideoConfigModel(
                    group_id=group_id,
                    video_ids=list(video_ids),
                    updated_by=updated_by,
                    version=1,
                )
                session.add(config)
            else:
                config.video_ids = list(video_ids)
                config.updated_by = updated_by
                config.version += 1

            await session.commit()

            video_map = {video.id: video for video in videos}
            ordered_videos = [
                self.serialize_video(video_map[video_id])
                for video_id in video_ids
                if video_id in video_map
            ]
            return {
                "group_id": group_id,
                "video_ids": list(video_ids),
                "videos": ordered_videos,
            }

    async def get_video_path(self, video_id: int) -> Path:
        """Resolve a video id to an existing local file."""

        video = await self.get_video_detail(video_id)
        file_path = Path(video.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")
        return file_path

    async def create_video(
        self,
        video_name: str,
        description: str | None = None,
        file_path: str | None = None,
        external_video_id: str | None = None,
    ) -> dict:
        """Create a new video metadata record."""

        await self.bootstrap()
        async with AsyncSessionLocal() as session:
            resolved_file_path = str(Path(file_path).resolve()) if file_path else ""
            file_name = Path(file_path).name if file_path else video_name
            mime_type = mimetypes.guess_type(file_name)[0] or "video/mp4"
            source_type = self.detect_source_type(file_name)
            is_available = bool(file_path and Path(file_path).exists())
            stored_file_path = (
                resolved_file_path
                if resolved_file_path
                else (
                    self.build_virtual_file_path(external_video_id)
                    if external_video_id
                    else self.build_virtual_file_path(video_name)
                )
            )

            existing_video = None
            if resolved_file_path:
                stmt = select(VideoModel).where(VideoModel.file_path == resolved_file_path)
                existing_video = (await session.execute(stmt)).scalar_one_or_none()

            if external_video_id:
                stmt = select(VideoModel).where(
                    VideoModel.external_video_id == external_video_id,
                )
                existing_external_video = (await session.execute(stmt)).scalar_one_or_none()
                if (
                    existing_external_video is not None
                    and existing_video is not None
                    and existing_external_video.id != existing_video.id
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="external_video_id already exists",
                    )
                if existing_video is None:
                    existing_video = existing_external_video

            if existing_video is not None:
                existing_video.is_deleted = False
                existing_video.external_video_id = external_video_id or existing_video.external_video_id
                existing_video.video_name = video_name
                existing_video.description = description
                existing_video.file_name = file_name
                existing_video.file_path = stored_file_path
                existing_video.source_type = source_type
                existing_video.file_size_bytes = (
                    Path(file_path).stat().st_size if is_available and file_path else None
                )
                existing_video.mime_type = mime_type
                existing_video.is_available = is_available
                existing_video.sync_status = (
                    VideoSyncStatus.synced.value if is_available else VideoSyncStatus.pending.value
                )

                if is_available and file_path:
                    await self.ensure_hls_assets(existing_video.id, Path(file_path))
                    existing_video.playback_type = self.detect_playback_type(existing_video.id)
                    existing_video.process_status = self.detect_process_status(existing_video.id)
                    existing_video.access_url = self.get_default_playback_url(existing_video.id)
                else:
                    existing_video.playback_type = VideoPlaybackType.mp4.value
                    existing_video.process_status = VideoProcessStatus.uploaded.value
                    existing_video.access_url = None

                await session.commit()
                return self.serialize_video(existing_video)

            video = VideoModel(
                group_id=None,
                external_video_id=external_video_id,
                video_name=video_name,
                description=description,
                file_name=file_name,
                file_path=stored_file_path,
                access_url="",
                source_type=source_type,
                playback_type=VideoPlaybackType.mp4.value,
                process_status=VideoProcessStatus.uploaded.value,
                duration_seconds=None,
                file_size_bytes=Path(file_path).stat().st_size if is_available and file_path else None,
                mime_type=mime_type,
                sync_status=(
                    VideoSyncStatus.synced.value if is_available else VideoSyncStatus.pending.value
                ),
                is_available=is_available,
            )
            session.add(video)
            await session.flush()

            if is_available and file_path:
                await self.ensure_hls_assets(video.id, Path(file_path))
                video.playback_type = self.detect_playback_type(video.id)
                video.process_status = self.detect_process_status(video.id)
                video.access_url = self.get_default_playback_url(video.id)

            await session.commit()
            return self.serialize_video(video)

    async def upload_video(
        self,
        upload_file: UploadFile,
        video_name: str,
        description: str | None = None,
        external_video_id: str | None = None,
    ) -> dict:
        """Persist an uploaded file locally and create/update its metadata."""

        await self.bootstrap()
        original_name = upload_file.filename or "video.mp4"
        suffix = Path(original_name).suffix.lower()
        if suffix not in {".mp4", ".mov", ".avi", ".mkv"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported video format",
            )

        file_token = self.sanitize_file_token(external_video_id or video_name)
        target_path = self.upload_dir / f"{file_token}{suffix}"

        async with AsyncSessionLocal() as session:
            existing_video = None
            if external_video_id:
                stmt = select(VideoModel).where(VideoModel.external_video_id == external_video_id)
                existing_video = (await session.execute(stmt)).scalar_one_or_none()

            if (
                existing_video is not None
                and existing_video.file_path
                and not existing_video.file_path.startswith("virtual://")
            ):
                target_path = Path(existing_video.file_path)
            elif target_path.exists():
                target_path = self.upload_dir / f"{file_token}_{uuid4().hex[:8]}{suffix}"

        await upload_file.seek(0)
        with target_path.open("wb") as file_obj:
            while True:
                chunk = await upload_file.read(1024 * 1024)
                if not chunk:
                    break
                file_obj.write(chunk)

        await upload_file.close()

        return await self.create_video(
            external_video_id=external_video_id,
            video_name=video_name,
            description=description,
            file_path=str(target_path),
        )

    async def delete_video(self, video_id: int) -> None:
        """Soft-delete a video and remove it from group configs."""

        await self.bootstrap()
        async with AsyncSessionLocal() as session:
            stmt = select(VideoModel).where(
                VideoModel.id == video_id,
                VideoModel.is_deleted == False,  # noqa: E712
            )
            video = (await session.execute(stmt)).scalar_one_or_none()
            if video is None:
                raise HTTPException(status_code=404, detail="Video not found")

            video.is_deleted = True
            video.is_available = False
            video.process_status = VideoProcessStatus.failed.value

            configs = (await session.execute(select(GroupVideoConfigModel))).scalars().all()
            for config in configs:
                if video_id in config.video_ids:
                    config.video_ids = [item for item in config.video_ids if item != video_id]
                    config.version += 1

            await session.commit()

        hls_dir = self.hls_root / str(video_id)
        if hls_dir.exists():
            shutil.rmtree(hls_dir, ignore_errors=True)

    async def save_batch_group_config(
        self,
        groups_payload: list[dict],
        updated_by: int | None = None,
    ) -> dict:
        """Persist the full frontend group payload."""

        await self.bootstrap()
        result_groups: list[dict] = []

        async with AsyncSessionLocal() as session:
            existing_videos = {
                item.external_video_id: item
                for item in (
                    await session.execute(
                        select(VideoModel).where(VideoModel.is_deleted == False)  # noqa: E712
                    )
                ).scalars().all()
                if item.external_video_id
            }

            for group_payload in groups_payload:
                group_id = int(group_payload["groupId"])
                group_name = group_payload["groupName"]
                if group_id not in {item[0] for item in self.FIXED_GROUPS}:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Unsupported group id: {group_id}",
                    )

                group = await self._require_group(session, group_id)
                group.group_name = group_name
                group.description = group_name

                ordered_video_ids: list[int] = []
                ordered_videos: list[dict] = []
                for video_item in group_payload.get("videos", []):
                    external_video_id = video_item["id"]
                    video = existing_videos.get(external_video_id)
                    if video is None:
                        video = VideoModel(
                            group_id=None,
                            external_video_id=external_video_id,
                            video_name=video_item["videoName"],
                            description=video_item.get("description"),
                            file_name=video_item["videoName"],
                            file_path=self.build_virtual_file_path(external_video_id),
                            access_url="",
                            source_type=VideoSourceType.unknown.value,
                            playback_type=VideoPlaybackType.mp4.value,
                            process_status=VideoProcessStatus.uploaded.value,
                            duration_seconds=None,
                            file_size_bytes=None,
                            mime_type=None,
                            sync_status=VideoSyncStatus.pending.value,
                            is_available=False,
                        )
                        session.add(video)
                        await session.flush()
                        existing_videos[external_video_id] = video
                    else:
                        video.video_name = video_item["videoName"]
                        video.description = video_item.get("description")
                    ordered_video_ids.append(video.id)
                    ordered_videos.append(self.serialize_video(video))

                config_stmt = select(GroupVideoConfigModel).where(
                    GroupVideoConfigModel.group_id == group_id
                )
                config = (await session.execute(config_stmt)).scalar_one_or_none()
                if config is None:
                    config = GroupVideoConfigModel(
                        group_id=group_id,
                        video_ids=ordered_video_ids,
                        updated_by=updated_by,
                        version=1,
                    )
                    session.add(config)
                else:
                    config.video_ids = ordered_video_ids
                    config.updated_by = updated_by
                    config.version += 1

                result_groups.append(
                    {
                        "group_id": group_id,
                        "video_ids": list(ordered_video_ids),
                        "videos": ordered_videos,
                    }
                )

            await session.commit()

        return {"groups": result_groups}

    def get_hls_manifest_path(self, video_id: int) -> Path:
        """Return the local HLS manifest path for a video."""

        return self.hls_root / str(video_id) / "index.m3u8"

    def get_hls_manifest_url(self, video_id: int) -> str:
        """Return the public HLS manifest URL for a video."""

        return f"/static_resources/hls/videos/{video_id}/index.m3u8"

    def get_stream_url(self, video_id: int) -> str:
        """Return the direct mp4 stream URL for a video."""

        return f"{base_configs.API_PREFIX}/demo/videos/{video_id}/stream"

    def get_download_url(self, video_id: int) -> str:
        """Return the direct download URL for the original source file."""

        return f"{base_configs.API_PREFIX}/videos/{video_id}/download"

    def get_default_playback_url(self, video_id: int) -> str:
        """Return HLS URL when available, otherwise direct mp4 stream."""

        if self.get_hls_manifest_path(video_id).exists():
            return self.get_hls_manifest_url(video_id)
        return self.get_stream_url(video_id)

    @staticmethod
    def detect_source_type(file_name: str) -> int:
        """Infer source type from file extension."""

        suffix = Path(file_name).suffix.lower()
        mapping = {
            ".mp4": VideoSourceType.mp4.value,
            ".mov": VideoSourceType.mov.value,
            ".avi": VideoSourceType.avi.value,
            ".mkv": VideoSourceType.mkv.value,
        }
        return mapping.get(suffix, VideoSourceType.unknown.value)

    def detect_playback_type(self, video_id: int) -> int:
        """Infer current playback type from generated assets."""

        if self.get_hls_manifest_path(video_id).exists():
            return VideoPlaybackType.hls.value
        return VideoPlaybackType.mp4.value

    def detect_process_status(self, video_id: int) -> int:
        """Infer processing status from generated assets."""

        if self.get_hls_manifest_path(video_id).exists():
            return VideoProcessStatus.ready.value
        return VideoProcessStatus.uploaded.value

    def resolve_ffmpeg_binary(self) -> str | None:
        """Resolve an available ffmpeg executable path."""

        configured = (getattr(base_configs, "FFMPEG_PATH", "") or "").strip()
        if configured:
            candidate = Path(configured)
            if candidate.exists():
                return str(candidate)
            if shutil.which(configured):
                return configured

        return shutil.which("ffmpeg")

    async def ensure_hls_assets(self, video_id: int, source_path: Path) -> None:
        """Generate HLS assets when ffmpeg is available."""

        ffmpeg_bin = self.resolve_ffmpeg_binary()
        if not ffmpeg_bin:
            return

        output_dir = self.hls_root / str(video_id)
        manifest_path = output_dir / "index.m3u8"
        source_mtime = source_path.stat().st_mtime

        if manifest_path.exists() and manifest_path.stat().st_mtime >= source_mtime:
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        for child in output_dir.iterdir():
            if child.is_file():
                child.unlink()

        command = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(source_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-f",
            "hls",
            "-hls_time",
            "4",
            "-hls_playlist_type",
            "vod",
            "-hls_segment_filename",
            str(output_dir / "segment_%03d.ts"),
            str(manifest_path),
        ]
        completed = await to_thread(
            subprocess.run,
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode != 0 and manifest_path.exists():
            manifest_path.unlink(missing_ok=True)

    @staticmethod
    async def _require_group(session, group_id: int) -> GroupModel:
        """Ensure a group exists."""

        stmt = select(GroupModel).where(
            GroupModel.id == group_id,
            GroupModel.is_deleted == False,  # noqa: E712
        )
        result = await session.execute(stmt)
        group = result.scalar_one_or_none()
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")
        return group


demo_service = DemoService()
