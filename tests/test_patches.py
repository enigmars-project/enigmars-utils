from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from enigmars_util.patches import (
    KernelRepoPatchStatus,
    OrgMigrationStatus,
    lts_pinned_tag,
    lts_tracks_in,
    migrate_org_in_text,
    offline_include_present,
    org_migration_needed_in,
    probe_kernel_repo_patch,
    retrack_lts_in_text,
)

STABLE_CONF = (
    "[linux-enigmarsos-lts]\n"
    "SigLevel = Optional TrustAll\n"
    "Server = https://github.com/enigmars-project/linux-enigmarsos/releases/download/lts\n"
)

PINNED_CONF = (
    "[linux-enigmarsos-lts]\n"
    "SigLevel = Optional TrustAll\n"
    "Server = https://github.com/enigmars-project/linux-enigmarsos/releases/download/linux-enigmarsos-lts-6.18.51\n"
)


class LtsTrackTest(unittest.TestCase):
    def test_stable_url_tracks(self) -> None:
        self.assertTrue(lts_tracks_in(STABLE_CONF))

    def test_pinned_tag_does_not_track(self) -> None:
        # A pinned .../download/linux-enigmarsos-lts-6.18.51 must not count.
        self.assertFalse(lts_tracks_in(PINNED_CONF))

    def test_commented_stable_ignored(self) -> None:
        self.assertFalse(lts_tracks_in("# Server = https://example.invalid/releases/download/lts\n"))

    def test_non_server_lines_ignored(self) -> None:
        self.assertFalse(lts_tracks_in("# releases/download/lts\n[linux-enigmarsos-lts]\n"))

    def test_retrack_rewrites_pinned_and_idempotent(self) -> None:
        self.assertEqual(retrack_lts_in_text(PINNED_CONF), STABLE_CONF)
        self.assertEqual(retrack_lts_in_text(STABLE_CONF), STABLE_CONF)
        commented = "# Server = https://example.invalid/releases/download/linux-enigmarsos-lts-6.18.51\n"
        self.assertEqual(retrack_lts_in_text(commented), commented)

    def test_pinned_tag_extracted(self) -> None:
        self.assertEqual(lts_pinned_tag(PINNED_CONF), "linux-enigmarsos-lts-6.18.51")

    def test_pinned_tag_none_when_tracking(self) -> None:
        self.assertIsNone(lts_pinned_tag(STABLE_CONF))
        self.assertIsNone(lts_pinned_tag("[linux-enigmarsos-lts]\n"))
        latest = STABLE_CONF.replace("releases/download/lts", "releases/latest/download")
        self.assertIsNone(lts_pinned_tag(latest))


class OfflineShadowTest(unittest.TestCase):
    def test_include_detected(self) -> None:
        text = "[options]\nInclude = /etc/pacman.d/enigmarsos-offline.conf\n"
        self.assertTrue(offline_include_present(text))

    def test_commented_include_ignored(self) -> None:
        self.assertFalse(offline_include_present("# Include = /etc/pacman.d/enigmarsos-offline.conf\n"))
        self.assertFalse(offline_include_present("[core]\nInclude = /etc/pacman.d/mirrorlist\n"))


class NeedsPatchTest(unittest.TestCase):
    def test_needs_patch_when_either_issue(self) -> None:
        self.assertTrue(KernelRepoPatchStatus(True, False, False).needs_patch)
        self.assertTrue(KernelRepoPatchStatus(False, True, False).needs_patch)
        self.assertTrue(KernelRepoPatchStatus(True, True, False).needs_patch)

    def test_healthy_needs_nothing(self) -> None:
        self.assertFalse(KernelRepoPatchStatus(False, False, False).needs_patch)

    def test_live_iso_never_needs_patch(self) -> None:
        self.assertFalse(KernelRepoPatchStatus(True, True, True).needs_patch)


class ProbeTest(unittest.TestCase):
    def _conf_path(self, content: str) -> Path:
        fh = tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False)
        fh.write(content)
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        return Path(fh.name)

    def test_shadow_detected(self) -> None:
        with (
            mock.patch("enigmars_util.patches._on_live_iso", return_value=False),
            mock.patch("enigmars_util.patches._pacman_si_repo", return_value="enigmarsos-offline"),
            mock.patch("enigmars_util.patches.LTS_CONF", self._conf_path(STABLE_CONF)),
            mock.patch(
                "enigmars_util.patches._read_text",
                side_effect=lambda p: (
                    "Include = /etc/pacman.d/enigmarsos-offline.conf\n"
                    if str(p) == "/etc/pacman.conf"
                    else STABLE_CONF
                ),
            ),
        ):
            status = probe_kernel_repo_patch()
        self.assertTrue(status.offline_shadows)
        self.assertFalse(status.lts_not_tracking)
        self.assertTrue(status.needs_patch)

    def test_pinned_lts_flags_not_tracking(self) -> None:
        with (
            mock.patch("enigmars_util.patches._on_live_iso", return_value=False),
            mock.patch("enigmars_util.patches._pacman_si_repo", return_value="linux-enigmarsos"),
            mock.patch("enigmars_util.patches.LTS_CONF", self._conf_path(PINNED_CONF)),
            mock.patch(
                "enigmars_util.patches._read_text",
                side_effect=lambda p: PINNED_CONF if "lts" in str(p) else "",
            ),
        ):
            status = probe_kernel_repo_patch()
        self.assertFalse(status.offline_shadows)
        self.assertTrue(status.lts_not_tracking)
        self.assertTrue(status.needs_patch)

    def test_missing_lts_conf_is_not_a_patch_issue(self) -> None:
        with (
            mock.patch("enigmars_util.patches._on_live_iso", return_value=False),
            mock.patch("enigmars_util.patches._pacman_si_repo", return_value=None),
            mock.patch("enigmars_util.patches.LTS_CONF", Path("/nonexistent-lts.conf")),
            mock.patch("enigmars_util.patches._read_text", return_value=""),
        ):
            status = probe_kernel_repo_patch()
        self.assertFalse(status.lts_not_tracking)
        self.assertFalse(status.needs_patch)

    def test_live_iso_suppresses_shadow(self) -> None:
        with (
            mock.patch("enigmars_util.patches._on_live_iso", return_value=True),
            mock.patch("enigmars_util.patches._pacman_si_repo", return_value="enigmarsos-offline"),
            mock.patch("enigmars_util.patches.LTS_CONF", Path("/nonexistent-lts.conf")),
            mock.patch("enigmars_util.patches._read_text", return_value=""),
        ):
            status = probe_kernel_repo_patch()
        self.assertTrue(status.on_live_iso)
        self.assertFalse(status.offline_shadows)
        self.assertFalse(status.needs_patch)

    def test_no_pacman_is_safe(self) -> None:
        import shutil

        with (
            mock.patch("enigmars_util.patches._on_live_iso", return_value=False),
            mock.patch.object(shutil, "which", return_value=None),
            mock.patch("enigmars_util.patches.LTS_CONF", Path("/nonexistent-lts.conf")),
            mock.patch("enigmars_util.patches._read_text", return_value=""),
        ):
            status = probe_kernel_repo_patch()
        self.assertFalse(status.needs_patch)


class OrgMigrationTest(unittest.TestCase):
    def test_old_org_flags(self) -> None:
        old = (
            "[linux-enigmarsos]\n"
            "SigLevel = Optional TrustAll\n"
            "Server = https://github.com/RishiSpace/linux-enigmarsos/releases/latest/download\n"
        )
        self.assertTrue(org_migration_needed_in(old))

    def test_new_org_clean(self) -> None:
        self.assertFalse(org_migration_needed_in(STABLE_CONF))
        self.assertFalse(org_migration_needed_in(PINNED_CONF))

    def test_commented_old_org_ignored(self) -> None:
        self.assertFalse(
            org_migration_needed_in("# Server = https://github.com/RishiSpace/linux-enigmarsos/releases/latest/download\n")
        )

    def test_migrate_rewrites_and_idempotent(self) -> None:
        old = "Server = https://github.com/RishiSpace/linux-enigmarsos/releases/latest/download\n"
        new = migrate_org_in_text(old)
        self.assertIn("github.com/enigmars-project/linux-enigmarsos", new)
        self.assertNotIn("RishiSpace", new)
        self.assertEqual(migrate_org_in_text(new), new)

    def test_status_needs_patch(self) -> None:
        self.assertTrue(OrgMigrationStatus(("a",)).needs_patch)
        self.assertFalse(OrgMigrationStatus(()).needs_patch)


if __name__ == "__main__":
    unittest.main()
