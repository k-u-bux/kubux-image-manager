{
  description = "Kubux AI Image Manager";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
                
        # Define Python environment with all required packages including together
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          tkinter
          pyside6
          pillow
          requests
          watchdog
          python-dotenv
        ]);
        
      in
      {
        packages.default = pkgs.stdenv.mkDerivation {
          pname = "kubux-image-manager";
          version = "0.9.1";
          
          src = ./.;
          
          buildInputs = [ pythonEnv pkgs.librsvg ];
          nativeBuildInputs = [ pkgs.makeWrapper ];
          
          installPhase = ''
            mkdir -p $out/bin
            mkdir -p $out/share/applications
	          mkdir -p $out/share/man/man1
	    
            # Copy the Python script
            cp kubux-image-manager.py $out/bin/kubux-image-manager.py
            chmod +x $out/bin/kubux-image-manager.py

	          # Copy the man page
	          cp kubux-image-manager.1 $out/share/man/man1

            # Create wrapper using makeWrapper for proper desktop integration
            makeWrapper ${pythonEnv}/bin/python $out/bin/kubux-image-manager \
              --add-flags "$out/bin/kubux-image-manager.py" \
              --set-default TMPDIR "/tmp"
	    
            # Copy desktop file
            cp kubux-image-manager.desktop $out/share/applications/

            # primary icon: scalable SVG
            mkdir -p $out/share/icons/hicolor/scalable/apps
            cp app-icon.svg $out/share/icons/hicolor/scalable/apps/kubux-image-manager.svg

            # fallback renderings for desktops that do not handle SVG
            for size in 16x16 22x22 24x24 32x32 48x48 64x64 96x96 128x128 192x192 256x256; do
              mkdir -p $out/share/icons/hicolor/$size/apps
              w=''${size%x*}; h=''${size#*x}
              rsvg-convert -w $w -h $h -o $out/share/icons/hicolor/$size/apps/kubux-image-manager.png app-icon.svg
            done
          '';
          
          meta = with pkgs.lib; {
            description = "AI-powered ai-image creation tool";
            homepage = "https://github.com/kubux/kubux-image-manager";
            license = licenses.asl20;
            maintainers = [ ];
            platforms = platforms.linux;
          };
        };
        
        # Development shell with all dependencies for efficient testing
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
	          python3
            pythonEnv
            imagemagick
            # Additional development tools
	          jetbrains.pycharm-community
	          python3Packages.scancode-toolkit
	          python3Packages.cython
            python3Packages.pip
            python3Packages.black
            python3Packages.flake8
          ];
          
          shellHook = ''
	          export SCANCODE_CACHE=$HOME/.cache/scancode-cache
	          export SCANCODE_LICENSE_INDEX_CACHE=$HOME/.cache/scancode-license-cache
	          ln -s $( which python ) python
            echo "Kubux Ai-Image Generator development environment"
            echo "Python with all dependencies available:"
            echo "  - tkinter, pillow, requests, python-dotenv"
            echo "  - together (from PyPI)"
            echo ""
            echo "You can now run: python kubux-image-manager.py"
	          echo ""
	          echo "A symlink to the actual python interpreter is provided for PyCharm"
	          cleanup() {
	            echo "Cleaning up development environment..."
		          rm -rf __pycache__
		          if [ -L ./python ]; then
      		      rm ./python
           		  fi
		          if [ -L ./result ]; then
      		      rm ./result
    		      fi
  	        }
  	        trap cleanup EXIT
          '';
        };
        
        # Dev shell for taking automated screenshots headlessly
        devShells.screenshot = pkgs.mkShell {
          buildInputs = with pkgs; [
            xorg.xvfb
            xdotool
            imagemagick
            pythonEnv
          ];
          shellHook = ''
            echo "=== kubux-image-manager screenshot shell ==="
            echo "Run: ./screenshots/screenshot.sh"
          '';
        };
      });
}