"""Read-only, hash-pinned access to explicitly assigned run files."""
from pathlib import Path
from threading import RLock
from desk_sources import digest,inside,write_json


class MissingAssignedReads(ValueError):
    def __init__(self, missing):
        self.missing = sorted(missing)
        super().__init__('Role did not read assigned files: '+', '.join(self.missing))


def reply_with_required_reads(store, request, on_missing=None):
    """One bounded correction for unread files; all other read failures remain fatal."""
    feedback = None
    for attempt in range(2):
        reply = request(feedback)
        if store is None:
            return reply
        try:
            store.verify()
        except MissingAssignedReads as error:
            if on_missing:
                on_missing(attempt + 1, error.missing)
            if attempt:
                raise
            feedback = ('Your reply is not accepted. Use read_assigned_file to read each missing file: '
                        + ', '.join(error.missing)
                        + '. Then return a complete response. Do not bypass this requirement.')
        else:
            return reply


class AssignedFiles:
    def __init__(self,run,paths,log):
        self.run=Path(run).resolve();self.log=Path(log)
        self.files={};self.reads=[];self.failure=None;self.lock=RLock()
        for path in paths:
            path=inside(self.run,Path(path).resolve())
            if not path.is_file():raise ValueError('Missing assigned file: '+str(path))
            self.files[path.relative_to(self.run).as_posix()]=digest(path)

    def manifest(self):
        return [{'file':name,'sha256':sha,'permission':'quote only; never recompute'}
                for name,sha in self.files.items()]

    def read(self,file):
        # Native providers can request several file tools in one response.
        # Serialize the shared access log, not the model's choice of files.
        with self.lock:return self._read(file)

    def _read(self,file):
        try:
            path=inside(self.run,file)
            name=path.relative_to(self.run).as_posix()
            if name not in self.files:raise ValueError('File is not assigned: '+file)
            if digest(path)!=self.files[name]:raise ValueError('Assigned file changed: '+name)
            text=path.read_text(encoding='utf-8')
            self.reads.append({'file':name,'sha256':self.files[name]})
            write_json(self.log,{'reads':self.reads})
            return '\n'.join(f'{name}:L{i}: {line}' for i,line in enumerate(text.splitlines(),1))
        except Exception as error:
            self.failure=str(error)
            write_json(self.log,{'reads':self.reads,'error':self.failure})
            raise

    def verify(self):
        if self.failure:raise ValueError(self.failure)
        missing=set(self.files)-{r['file'] for r in self.reads}
        if missing:raise MissingAssignedReads(missing)
        for name,sha in self.files.items():
            if digest(inside(self.run,name))!=sha:raise ValueError('Assigned file changed: '+name)


def file_tool(store):
    # Import only when a real crew is constructed. Offline tests can exercise
    # the same store without creating a CrewAI runtime.
    from crewai.tools import BaseTool,ToolFailure
    from pydantic import BaseModel
    class ReadInput(BaseModel):
        file:str
    class ReadAssignedFile(BaseTool):
        name:str='read_assigned_file'
        description:str='Read an assigned saved output file. Quote its exact lines; never recompute values. No other file access is allowed.'
        args_schema:type[BaseModel]=ReadInput
        def _run(self,file:str):
            try:return store.read(file)
            except Exception as error:return ToolFailure(message=str(error),retryable=False)
    result=ReadAssignedFile()
    result.cache_function=lambda args,value:False
    return result
