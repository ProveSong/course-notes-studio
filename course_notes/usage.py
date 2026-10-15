"""Actual provider usage, not a character-to-token guess."""
from .config import ROOT
from .jsonstore import transaction

def record_usage(transport,model,prompt,images,usage):
    with transaction(ROOT/'llm-usage.json') as rows:
        rows.append({'transport':transport,'model':model,'input_characters':len(prompt),
                     'images':len(images),'usage':usage or {}})
