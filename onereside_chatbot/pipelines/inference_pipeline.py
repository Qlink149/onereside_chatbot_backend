from onereside_chatbot.pipelines.pipeline import Pipeline
from onereside_chatbot.processors.classifier import Classifier
from onereside_chatbot.processors.qr_processor import QRProcessor
from onereside_chatbot.processors.general_agent import GeneralAgent
from onereside_chatbot.processors.product_search_agent import ProductAgent
from onereside_chatbot.processors.one_reside_agent import OneResideAgent
from onereside_chatbot.processors.user_registration import (
    UserRegistration,
)


class InitialPipeline(Pipeline):
    """Pipeline class for inital user registartion and service list."""

    def __init__(self) -> None:
        processors = [UserRegistration(), QRProcessor(), Classifier()]
        super().__init__(processors)


class GeneralPipeline(Pipeline):
    """Pipeline class for general."""

    def __init__(self) -> None:
        processors = [GeneralAgent()]
        super().__init__(processors)

class ProductSearchPipeline(Pipeline):
    """Pipeline class for search."""

    def __init__(self) -> None:
        processors = [ProductAgent()]
        super().__init__(processors)
        
class OneResidePipeline(Pipeline):
    """Pipeline class for one reside."""

    def __init__(self) -> None:
        processors = [OneResideAgent()]
        super().__init__(processors)
