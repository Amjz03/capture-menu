"""Launch Capture Menu from source or the packaged Windows executable."""
from capturemenu import runtime


if __name__ == "__main__":
    runtime.leave_if_not_needed()      # the scheduled --watch check, before Qt loads (see runtime.ALIVE)
    from capturemenu.app import main
    main()
