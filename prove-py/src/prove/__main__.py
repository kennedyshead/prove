import warnings

warnings.filterwarnings("ignore", message="nltk.app.wordfreq not loaded", category=UserWarning)

from prove.cli import main  # noqa: E402

main()
