"""Audio specialization of the shared stream detector contract."""

from mediaqc_engine.detectors.common import (
    StreamDetector,
)
from mediaqc_engine.detectors.common import (
    number as number,
)
from mediaqc_engine.detectors.common import (
    pairs as pairs,
)
from mediaqc_engine.detectors.common import (
    settings as settings,
)


class AudioDetector(StreamDetector):
    media_type = "audio"
