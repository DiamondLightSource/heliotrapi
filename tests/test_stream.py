from collections.abc import AsyncGenerator

from heliotrapi.analysis_core.registry import get_analysis
from heliotrapi.models import AnalysisStream, AnalysisStreamRequest, StreamUpdate
from heliotrapi.task_queue.streaming import run_stream_analysis


class TestAnalysisStreamAppend:
    def test_append_stream_update_without_z(self):
        stream = AnalysisStream(x=[1], y=[2])
        update = StreamUpdate(x=3, y=4)

        stream.append(update)

        assert stream.x == [1, 3]
        assert stream.y == [2, 4]
        assert stream.z is None

    def test_append_stream_update_with_z(self):
        stream = AnalysisStream(
            x=[1],
            y=[2],
            z=[3],
        )
        update = StreamUpdate(
            x=4,
            y=5,
            z=6,
        )

        stream.append(update)

        assert stream.x == [1, 4]
        assert stream.y == [2, 5]
        assert stream.z == [3, 6]

    def test_append_analysis_stream_without_z(self):
        stream = AnalysisStream(
            x=[1],
            y=[2],
        )
        other = AnalysisStream(
            x=[3, 4],
            y=[5, 6],
        )

        stream.append(other)

        assert stream.x == [1, 3, 4]
        assert stream.y == [2, 5, 6]
        assert stream.z is None

    def test_append_analysis_stream_with_z(self):
        stream = AnalysisStream(
            x=[1],
            y=[2],
            z=[3],
        )
        other = AnalysisStream(
            x=[4, 5],
            y=[6, 7],
            z=[8, 9],
        )

        stream.append(other)

        assert stream.x == [1, 4, 5]
        assert stream.y == [2, 6, 7]
        assert stream.z == [3, 8, 9]

    def test_append_skips_z_when_self_z_is_none(self):
        stream = AnalysisStream(
            x=[],
            y=[],
            z=None,
        )
        other = AnalysisStream(
            x=[1],
            y=[2],
            z=[3],
        )

        stream.append(other)

        assert stream.x == [1]
        assert stream.y == [2]
        assert stream.z is None

    def test_append_skips_z_when_other_z_is_none(self):
        stream = AnalysisStream(
            x=[],
            y=[],
            z=[10],
        )
        other = AnalysisStream(
            x=[1],
            y=[2],
            z=None,
        )

        stream.append(other)

        assert stream.x == [1]
        assert stream.y == [2]
        assert stream.z == [10]

    def test_append_preserves_int_and_float_values(self):
        stream = AnalysisStream(
            x=[1],
            y=[2.5],
            z=[3],
        )
        other = AnalysisStream(
            x=[4.5],
            y=[6],
            z=[7.25],
        )

        stream.append(other)

        assert stream.x == [1, 4.5]
        assert stream.y == [2.5, 6]
        assert stream.z == [3, 7.25]


class TestAnalysisStreamAdd:
    def test_add_mutates_left_hand_side(self):
        stream = AnalysisStream(x=[1], y=[2])
        update = StreamUpdate(x=3, y=4)

        result = stream + update

        assert stream.x == [1, 3]
        assert stream.y == [2, 4]

        # current implementation returns append(...)
        assert result is None

    def test_add_analysis_stream(self):
        stream = AnalysisStream(x=[1], y=[2])
        other = AnalysisStream(x=[3], y=[4])

        result = stream + other

        assert stream.x == [1, 3]
        assert stream.y == [2, 4]
        assert result is None


def test_run_stream_analysis_is_async():

    double_fn = get_analysis("double")

    analysis_stream = run_stream_analysis(
        double_fn, inputs={"number": 5}, max_iterations=10
    )

    assert isinstance(analysis_stream, AsyncGenerator)


def test_create_stream():

    stream_double = AnalysisStreamRequest(
        analysis_name="double", inputs={"number": 5}, max_iterations=10
    )

    assert stream_double
