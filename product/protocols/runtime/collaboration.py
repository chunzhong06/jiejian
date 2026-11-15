"""协作阅读的嵌套说明；只描述目标与问题，不携带授权、完成状态或业务结论。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CollaborationOutput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)
    kind: Literal['FLOW', 'PROOF', 'SCENARIO']
    label: str = Field(min_length=1, max_length=80, pattern=r'\S')


class CollaborationBrief(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)
    title: str = Field(min_length=1, max_length=80, pattern=r'\S')
    objective: str = Field(default='', max_length=240)
    outputs: list[CollaborationOutput] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def distinct_output_groups(self):
        if len({item.kind for item in self.outputs})!=len(self.outputs):
            raise ValueError('每类产物只保留一个交付目标组')
        return self


class QuestionPresentation(BaseModel):
    """title 是用户需要回答的具体问题，reason 解释用途；技术原文仍由原问题保存。"""
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)
    title: str = Field(min_length=1, max_length=80, pattern=r'\S')
    reason: str = Field(min_length=1, max_length=240, pattern=r'\S')
    answer_hint: str = Field(default='', max_length=160)
