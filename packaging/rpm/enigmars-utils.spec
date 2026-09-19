%global debug_package %{nil}

Name:           enigmars-utils
Version:        @@VERSION@@
Release:        1
Summary:        Qt landing hub for Linux (tweaks, packages, kernels, Secure Boot)
License:        GPLv3+
URL:            https://github.com/enigmars-project/enigmars-utils
BuildArch:      noarch
Requires:       python3 >= 3.12
Requires:       polkit
Requires:       python3-pyside6

%description
Enigmars Utils detects the distro, desktop, and package manager, then offers
Windows-convert tweaks, package actions, kernel management, and sbctl-based
Secure Boot setup. The GUI never runs as root; privileged work uses pkexec.

%prep
true

%build
true

%install
DESTDIR=%{buildroot} PREFIX=/usr %{srcroot}/scripts/install.sh
find %{buildroot} -type d -name '__pycache__' -prune -exec rm -rf {} +
find %{buildroot} -type f -name '*.pyc' -delete

%files
/usr/bin/enigmars-util
/usr/libexec/enigmars-util-helper
/usr/lib/enigmars-utils
/usr/share/enigmars-util
/usr/share/applications/org.enigmars.Util.desktop
/usr/share/applications/org.enigmars.Fun-Meow.desktop
/usr/share/icons/hicolor/scalable/apps/enigmarsos.svg
/usr/share/icons/hicolor/scalable/apps/org.enigmars.Util.svg
/usr/share/icons/hicolor/256x256/apps/enigmarsos.png
/usr/share/pixmaps/enigmarsos.png
/usr/share/polkit-1/actions/org.enigmars.util.policy

%changelog
* Sat Sep 19 2026 RishiSpace <rishikesh.giridhar@outlook.com> - 1.2.0-1
- Fun page: Cat Mode with KDE login/logout event sounds, CI-hermetic tests.
* Mon Aug 31 2026 RishiSpace <rishikesh.giridhar@outlook.com> - 1.1.2-1
- Initial RPM package.
