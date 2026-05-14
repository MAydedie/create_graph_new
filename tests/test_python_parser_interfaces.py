from pathlib import Path

from parsers.python_parser import PythonASTVisitor


class _DummySymbolTable:
    pass


def _visit_source(source: str):
    import ast

    visitor = PythonASTVisitor(Path('sample.py'), _DummySymbolTable())
    visitor.visit(ast.parse(source, filename='sample.py'))
    return visitor


def test_python_parser_marks_interface_like_bases_as_interfaces():
    visitor = _visit_source(
        'class Service(BaseService, IService, AnotherProtocol):\n'
        '    pass\n'
    )

    class_info = visitor.classes['Service']
    assert class_info.parent_class == 'BaseService'
    assert class_info.interfaces == ['IService', 'AnotherProtocol']


def test_python_parser_keeps_additional_mixins_as_interfaces_when_parent_exists():
    visitor = _visit_source(
        'class Repository(SqlAlchemyBase, TimestampMixin, SoftDeleteMixin):\n'
        '    pass\n'
    )

    class_info = visitor.classes['Repository']
    assert class_info.parent_class == 'SqlAlchemyBase'
    assert class_info.interfaces == ['TimestampMixin', 'SoftDeleteMixin']
