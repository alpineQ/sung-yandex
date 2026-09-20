{
  description = "Sung Yandex — native Qt Quick player with yamusic-compatible disk cache";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }: let
    pkgs = nixpkgs.legacyPackages.x86_64-linux;
    buildInputs = with pkgs.qt6; [ qtbase qtdeclarative qtmultimedia qtsvg qtwayland qtimageformats ];
    nativeBuildInputs = with pkgs; [ cmake ninja pkg-config python3 libsecret qt6.wrapQtAppsHook ];
  in {
    packages.x86_64-linux.default = pkgs.stdenv.mkDerivation {
      pname = "sung-yandex";
      version = "0.1.0";
      src = self;
      inherit buildInputs nativeBuildInputs;
      cmakeFlags = [ "-DBUILD_TESTING=OFF" ];
      qtWrapperArgs = [ "--prefix" "PATH" ":" (pkgs.lib.makeBinPath [ pkgs.python3 pkgs.ffmpeg pkgs.libsecret ]) ];
      meta.mainProgram = "sung-yandex";
    };
    devShells.x86_64-linux.default = pkgs.mkShell {
      inherit buildInputs;
      nativeBuildInputs = nativeBuildInputs ++ [ pkgs.python3 pkgs.ffmpeg pkgs.dbus ];
      QT_QPA_PLATFORM_PLUGIN_PATH = "${pkgs.qt6.qtbase}/lib/qt-6/plugins";
      QT_PLUGIN_PATH = pkgs.lib.makeSearchPath "lib/qt-6/plugins" buildInputs;
      QML_IMPORT_PATH = pkgs.lib.makeSearchPath "lib/qt-6/qml" buildInputs;
    };
  };
}
