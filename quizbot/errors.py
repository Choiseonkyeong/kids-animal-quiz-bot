class QuizBotError(Exception):
    """프로그램 공통 예외."""


class ScriptValidationError(QuizBotError):
    """대본 JSON이 스키마·규칙을 만족하지 않음."""


class ScriptGenerationError(QuizBotError):
    """재시도 후에도 대본 생성 실패."""


class TTSError(QuizBotError):
    pass


class ImageGenerationError(QuizBotError):
    pass


class AssetMissingError(QuizBotError):
    pass


class RenderError(QuizBotError):
    pass


class UploadError(QuizBotError):
    pass
