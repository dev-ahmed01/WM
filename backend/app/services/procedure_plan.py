"""Convert reviewed visual procedure plans to the EXISTING OWD compiler grammar.

This never trusts extraction as a published SOP. Validation happens against the
canonical OWD parser+validator, not a second compiler. Every step is a separate
state, preserving the evidence-to-step relationship already used in Phase 2.
"""
from __future__ import annotations

import re
import yaml

from app.compiler.pipeline import OWDCompilerPipeline

OUTPUTS=frozenset(("CONFIRMATION","TEXT_INPUT","NUMERIC_INPUT","DOCUMENT_UPLOAD"))
EVIDENCE=frozenset(("NONE","PHOTO_JPEG","DOCUMENT_PDF"))
OPT_CODE=re.compile(r"^[A-Z][A-Z0-9_]{1,30}$")
ID_CODE=re.compile(r"^[a-zA-Z0-9_-]{4,40}$")


class ProcedurePlanError(ValueError):
    pass


def check_plan(steps:list[dict], decision:dict | None) -> tuple[list[dict],dict]:
    if not isinstance(steps,list) or not 1<=len(steps)<=50:
        raise ProcedurePlanError("A plan needs 1 to 50 operational steps.")
    ids=set()
    validated=[]
    for item in steps:
        if not isinstance(item,dict):
            raise ProcedurePlanError("Malformed procedure step.")
        id_=item.get("id")
        text=item.get("instruction")
        if not isinstance(id_,str) or not ID_CODE.fullmatch(id_) or id_ in ids:
            raise ProcedurePlanError("Every step needs a unique safe identifier.")
        ids.add(id_)
        if not isinstance(text,str) or not 10<=len(text.strip())<=700:
            raise ProcedurePlanError("Each work instruction must contain 10 to 700 characters.")
        output=item.get("output_type","CONFIRMATION")
        proof=item.get("evidence_type","NONE")
        if output not in OUTPUTS or proof not in EVIDENCE:
            raise ProcedurePlanError("Unsupported output or evidence requirement.")
        if output=="DOCUMENT_UPLOAD" and proof=="NONE":
            raise ProcedurePlanError("Document-upload checkpoints must require a photo or PDF.")
        if item.get("reviewed") is not True:
            raise ProcedurePlanError("Every step must be reviewed against the original source.")
        validated.append(dict(item,output_type=output,evidence_type=proof))
    decision=decision or {"question":"","options":[]}
    if not isinstance(decision,dict):
        raise ProcedurePlanError("The final decision must be an object.")
    opts=decision.get("options",[])
    question=decision.get("question","")
    if not isinstance(opts,list) or len(opts) not in (0,2,3):
        raise ProcedurePlanError("Choose no outcome decision, or 2–3 explicit outcomes.")
    if not isinstance(question,str):
        raise ProcedurePlanError("Decision question is invalid.")
    if opts and not 10<=len(question.strip())<=220:
        raise ProcedurePlanError("An outcome question is required for branching.")
    codes=set()
    labels=set()
    for opt in opts:
        if not isinstance(opt,dict):
            raise ProcedurePlanError("Invalid outcome.")
        code,label=opt.get("code"),opt.get("label")
        if not isinstance(code,str) or not OPT_CODE.fullmatch(code) or code in codes:
            raise ProcedurePlanError("Outcome codes must be unique uppercase identifiers.")
        if not isinstance(label,str) or not 3<=len(label.strip())<=120 or label.casefold() in labels:
            raise ProcedurePlanError("Each outcome label must be unique and meaningful.")
        codes.add(code);labels.add(label.casefold())
    return validated,{"question":question.strip(),"options":opts}


def render_owd(draft:dict)->str:
    steps,decision=check_plan(draft["steps"],draft.get("decision"))
    code="SOP_DRAFT_"+draft["id"].split("_",1)[-1].upper()
    title=str(draft["title"]).replace("\n"," ").replace("\r"," ").strip()
    if not 5<=len(title)<=180:
        raise ProcedurePlanError("Invalid workflow title.")
    lines=[f"# {code}: {title}",""]
    for index,step in enumerate(steps,1):
        current=f"STATE_STEP_{index:02d}"
        next_state=(f"STATE_STEP_{index+1:02d}" if index<len(steps) else
                    "STATE_OUTCOME_DECISION" if decision["options"] else "STATE_FINISHED")
        lines.extend([
            f'::state[{current}]{{type="ATOMIC_STEP" is_initial={"true" if index==1 else "false"}}}',
            f"# State {index}: Checkpoint {index}",
            f":::step[STEP_{index:02d}]",
            yaml.safe_dump({
                "instruction":step["instruction"],
                "output_type":step["output_type"],
                "mandatory":True,
            },sort_keys=False,allow_unicode=True,width=10000).rstrip(),
            ":::",
        ])
        if step["evidence_type"]!="NONE":
            lines.extend([
                f':::evidence[PROOF_{index:02d}]{{type="{step["evidence_type"]}" required=true}}',
                "Evidence required before this checkpoint can be recorded.",
                ":::",
            ])
        lines.extend([f'::transition{{to="{next_state}" condition="ALWAYS"}}',""])
    if decision["options"]:
        lines.extend([
            '::state[STATE_OUTCOME_DECISION]{type="DECISION"}',
            "# State: Record the final observed outcome",
            ":::decision[DEC_OUTCOME]",
            yaml.safe_dump({
                "question":decision["question"],
                "options":[
                    {"option_code":opt["code"],"label":opt["label"],
                     "next_state":f"STATE_RESULT_{i+1:02d}"}
                    for i,opt in enumerate(decision["options"])
                ],
            },sort_keys=False,allow_unicode=True,width=10000).rstrip(),
            ":::","",
        ])
        for i,opt in enumerate(decision["options"]):
            lines.extend([
                f'::state[STATE_RESULT_{i+1:02d}]{{type="END" is_terminal=true}}',
                f"# State: {opt['label'].replace(chr(10),' ').replace(chr(13),' ')}",
                "Recording this outcome completes the inspection record, not external safety approval.",
                "",
            ])
    else:
        lines.extend([
            '::state[STATE_FINISHED]{type="END" is_terminal=true}',
            "# State: Procedure record completed",
            "This terminal state certifies recorded steps, not independent physical compliance.",
            "",
        ])
    return "\n".join(lines)


def compile_preview(draft:dict,version_number:int=1)->dict:
    try:
        owd=render_owd(draft)
        result=OWDCompilerPipeline.process_owd(
            markdown_text=owd,title=draft["title"],
            department_id=draft["department_id"],
            user_id=draft["created_by"],
            source_filename="reviewed_procedure.md",
            version_number=version_number,skip_loader=True,
        )
    except ProcedurePlanError:
        raise
    except Exception as exc:
        raise ProcedurePlanError("The established OWD compiler rejected the generated procedure.") from exc
    return {
        "valid":result["compilation_status"]=="SUCCESS",
        "validation_errors":result.get("validation_errors",[]),
        "warnings":result.get("warnings",[]),
        "steps":result.get("number_of_steps",0),
        "states":result.get("number_of_states",0),
        "decisions":result.get("number_of_decisions",0),
        "version_number":version_number,
        "markdown":owd,
    }
