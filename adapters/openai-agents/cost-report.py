#!/usr/bin/env python3
"""Refresh an attributed task estimate with existing Agents read access; no inference."""
import argparse
import importlib.util
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'tools'))
import episodes as e
import task_costs
import failures
spec=importlib.util.spec_from_file_location('cost_backend',HERE/'marmot-backend.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--instance',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();config=b.read(a.instance);path=a.report.resolve()
    if not path.is_relative_to(Path(config['state_root']).resolve()) or path.parent.name not in ('task-costs','task-costs-ppq'):raise ValueError('Report must belong to this instance task-costs state')
    value=e.read(path)
    if value['state']!='closed':raise ValueError('Active tasks are observed by the adapter; finish the scope first')
    _,api,_=b.model_client(dict(config,state_root=str(path.parent.parent)))
    turns=b.paged(api,'sessions/'+value['session_id']+'/turns')
    value=task_costs.refresh(path,value['session_id'],turns);print(task_costs.notice(value))

if __name__=='__main__':failures.cli(main,'controller')
