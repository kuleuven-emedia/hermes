############
#
# Copyright (c) 2024-2026 Maxim Yudayev and KU Leuven eMedia Lab
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Created 2024-2025 for the KU Leuven AidWear, AidFOG, and RevalExo projects
# by Maxim Yudayev [https://yudayev.com].
#
# ############

from multiprocessing import Queue

from hermes.base.nodes.node import Node
from hermes.base.nodes.node_interface import NodeInterface
from hermes.utils.di_utils import search_module_class


def launch_node(spec: dict, input_queue: "Queue[tuple[float, str]]"):
    """Launches callable `Node` objects using the user-provided specification.

    Args:
        spec (dict): Specification containing at least package and `Node` names, and constructor arguments specific to that `Node`.
        input_queue (Queue[tuple[float, str]]): Multiprocessing queue to fan-in user keyboard inputs if the `Node` is interested to receive any.
    """
    topic_name: str = spec["topic"]
    module_name: str = spec["package"]
    class_name: str = spec["class"]
    class_args: dict = spec["settings"]
    node_class: type[NodeInterface] = search_module_class(module_name, class_name)
    node: Node = node_class(topic=topic_name, **class_args, input_queue=input_queue)
    node()
