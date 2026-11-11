"""gRPC-сервер тих самих метеоданих (урок 32).

Контракт — meteo.proto. Python-код з нього генерує grpcio-tools при першому імпорті
(у папку _generated/, яку не комітимо): так роблять у проєктах — у git лежить лише .proto.

    from meteo_api.grpc_meteo import start_grpc_server, connect
    target = start_grpc_server()          # 127.0.0.1:50051
    stub, pb2 = connect(target)
    print(stub.GetLatest(pb2.StationRequest(wmo="34504")))
"""
import sys
from concurrent import futures
from pathlib import Path

import grpc

HERE = Path(__file__).parent
GENERATED = HERE / "_generated"


def _load_generated():
    if not (GENERATED / "meteo_pb2.py").exists():
        from grpc_tools import protoc
        GENERATED.mkdir(exist_ok=True)
        code = protoc.main(["protoc", f"-I{HERE}", f"--python_out={GENERATED}",
                            f"--grpc_python_out={GENERATED}", str(HERE / "meteo.proto")])
        if code != 0:
            raise RuntimeError("protoc не зміг скомпілювати meteo.proto")
    if str(GENERATED) not in sys.path:
        sys.path.insert(0, str(GENERATED))
    import meteo_pb2
    import meteo_pb2_grpc
    return meteo_pb2, meteo_pb2_grpc


pb2, pb2_grpc = _load_generated()


def _to_message(obs):
    from .storage import format_time
    return pb2.Observation(station=obs["station"], time=format_time(obs["time"]),
                           temperature=obs["temperature"] or 0.0, pressure=obs.get("pressure") or 0.0)


class MeteoService(pb2_grpc.MeteoServicer):
    def __init__(self, repo):
        self.repo = repo

    def GetLatest(self, request, context):
        from .storage import NotFoundError
        try:
            items = self.repo.list_observations(request.wmo)
        except NotFoundError as e:
            context.abort(grpc.StatusCode.NOT_FOUND, str(e))
        if not items:
            context.abort(grpc.StatusCode.NOT_FOUND, f"немає спостережень станції {request.wmo}")
        return _to_message(items[-1])

    def StreamObservations(self, request, context):
        for obs in self.repo.list_observations(request.wmo):
            yield _to_message(obs)


_server = None


def start_grpc_server(repo=None, port=50051):
    """Запустити gRPC-сервер у фонових потоках (один раз) і повернути адресу."""
    global _server
    if _server is None:
        from .storage import MeteoRepository
        _server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        pb2_grpc.add_MeteoServicer_to_server(MeteoService(repo or MeteoRepository.default()), _server)
        _server.add_insecure_port(f"127.0.0.1:{port}")
        _server.start()
    return f"127.0.0.1:{port}"


def connect(target):
    """Клієнтський stub: методи сервера викликаються як звичайні функції."""
    return pb2_grpc.MeteoStub(grpc.insecure_channel(target)), pb2
