"""What the packaged app runs. (src/marginalia/__main__.py uses a relative import, which a frozen
top-level script can't.)"""
import multiprocessing

# Libraries we bundle start multiprocessing helpers (a resource tracker). In a frozen app those
# re-launch this executable with interpreter flags; freeze_support() runs them instead of the app.
multiprocessing.freeze_support()

from marginalia.app import main  # noqa: E402

main()
