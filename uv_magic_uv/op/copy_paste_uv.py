# <pep8-80 compliant>

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

__author__ = "imdjs, Nutti <nutti.metro@gmail.com>"
__status__ = "production"
__version__ = "5.1"
__date__ = "24 Feb 2018"

import math
from math import atan2, sin, cos

import bpy
import bmesh
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    EnumProperty,
)
from mathutils import Vector

from .. import common


__all__ = [
    'MUV_CPUVCopyUV',
    'MUV_CPUVCopyUVMenu',
    'MUV_CPUVPasteUV',
    'MUV_CPUVPasteUVMenu',
    'MUV_CPUVSelSeqCopyUV',
    'MUV_CPUVSelSeqCopyUVMenu',
    'MUV_CPUVSelSeqPasteUV',
    'MUV_CPUVSelSeqPasteUVMenu',
]


def is_valid_context(context):
    obj = context.object

    # only edit mode is allowed to execute
    if obj is None:
        return False
    if obj.type != 'MESH':
        return False
    if context.object.mode != 'EDIT':
        return False

    # only 'VIEW_3D' space is allowed to execute
    for space in context.area.spaces:
        if space.type == 'VIEW_3D':
            break
    else:
        return False

    return True


class MUV_CPUVCopyUV(bpy.types.Operator):
    """
    Operation class: Copy UV coordinate
    """

    bl_idname = "uv.muv_cpuv_copy_uv"
    bl_label = "Copy UV"
    bl_description = "Copy UV coordinate"
    bl_options = {'REGISTER', 'UNDO'}

    uv_map = StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return is_valid_context(context)

    def execute(self, context):
        props = context.scene.muv_props.cpuv
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        if common.check_version(2, 73, 0) >= 0:
            bm.faces.ensure_lookup_table()

        # get UV layer
        uv_layers = []
        if self.uv_map == "__default":
            if not bm.loops.layers.uv:
                self.report(
                    {'WARNING'}, "Object must have more than one UV map")
                return {'CANCELLED'}
            uv_layers.append(bm.loops.layers.uv.verify())
            self.report({'INFO'}, "Copy UV coordinate")
        elif self.uv_map == "__all":
            for layer in bm.loops.layers.uv:
                uv_layers.append(layer)
        else:
            uv_layers.append(bm.loops.layers.uv[self.uv_map])
            self.report(
                {'INFO'}, "Copy UV coordinate (UV map:%s)" % (self.uv_map))

        # get selected face
        props.src_info = {}
        for layer in uv_layers:
            face_info = []
            for face in bm.faces:
                if face.select:
                    info = {
                        "src_uvs": [l[layer].uv.copy() for l in face.loops],
                        "src_pin_uvs": [l[layer].pin_uv for l in face.loops],
                        "src_seams": [l.edge.seam for l in face.loops],
                    }
                    face_info.append(info)
            if not face_info:
                self.report({'WARNING'}, "No faces are selected")
                return {'CANCELLED'}
            props.src_info[layer] = face_info

        self.report({'INFO'}, "%d face(s) are selected" % len(props.src_uvs))

        return {'FINISHED'}


class MUV_CPUVCopyUVMenu(bpy.types.Menu):
    """
    Menu class: Copy UV coordinate
    """

    bl_idname = "uv.muv_cpuv_copy_uv_menu"
    bl_label = "Copy UV (Menu)"
    bl_description = "Menu of Copy UV coordinate"

    @classmethod
    def poll(cls, context):
        return is_valid_context(context)

    def draw(self, context):
        layout = self.layout
        # create sub menu
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        uv_maps = bm.loops.layers.uv.keys()

        ops = layout.operator(MUV_CPUVCopyUV.bl_idname, text="[Default]")
        ops.uv_map = "__default"
        ops = layout.operator(MUV_CPUVCopyUV.bl_idname, text="[All]")
        ops.uv_map = "__all"

        for m in uv_maps:
            ops = layout.operator(MUV_CPUVCopyUV.bl_idname, text=m)
            ops.uv_map = m


class MUV_CPUVPasteUV(bpy.types.Operator):
    """
    Operation class: Paste UV coordinate
    """

    bl_idname = "uv.muv_cpuv_paste_uv"
    bl_label = "Paste UV"
    bl_description = "Paste UV coordinate"
    bl_options = {'REGISTER', 'UNDO'}

    uv_map = StringProperty(options={'HIDDEN'})
    strategy = EnumProperty(
        name="Strategy",
        description="Paste Strategy",
        items=[
            ('N_N', 'N:N', 'Number of faces must be equal to source'),
            ('N_M', 'N:M', 'Number of faces must not be equal to source')
        ],
        default="N_M"
    )
    flip_copied_uv = BoolProperty(
        name="Flip Copied UV",
        description="Flip Copied UV...",
        default=False
    )
    rotate_copied_uv = IntProperty(
        default=0,
        name="Rotate Copied UV",
        min=0,
        max=30
    )
    copy_seams = BoolProperty(
        name="Copy Seams",
        description="Copy Seams",
        default=True
    )

    @classmethod
    def poll(cls, context):
        sc = context.scene
        props = sc.muv_props.cpuv
        if not props.src_info:
            return False
        return is_valid_context(context)

    def execute(self, context):
        props = context.scene.muv_props.cpuv
        if not props.src_info:
            self.report({'WARNING'}, "Need copy UV at first")
            return {'CANCELLED'}
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        if common.check_version(2, 73, 0) >= 0:
            bm.faces.ensure_lookup_table()

        # get UV layer
        uv_layers = []
        if self.uv_map == "__default":
            if not bm.loops.layers.uv:
                self.report(
                    {'WARNING'}, "Object must have more than one UV map")
                return {'CANCELLED'}
            uv_layers.append(bm.loops.layers.uv.verify())
            self.report({'INFO'}, "Paste UV coordinate")
        elif self.uv_map == "__new":
            uv_maps_old = {l.name for l in obj.data.uv_layers}
            bpy.ops.mesh.uv_texture_add()
            uv_maps_new = {l.name for l in obj.data.uv_layers}
            diff = uv_maps_new - uv_maps_old
            bm = bmesh.from_edit_mesh(obj.data)
            if common.check_version(2, 73, 0) >= 0:
                bm.faces.ensure_lookup_table()
            uv_layers.append(bm.loops.layers.uv[list(diff)[0]])
            self.report(
                {'INFO'}, "Paste UV coordinate (UV map:%s)" % (list(diff)[0]))
        elif self.uv_map == "__all":
            uv_layers = props.src_info.keys()
        else:
            uv_layers.append(bm.loops.layers.uv[self.uv_map])
            self.report(
                {'INFO'}, "Paste UV coordinate (UV map:%s)" % (self.uv_map))

        # get selected face
        dest_info = []
        for face in bm.faces:
            if face.select:
                info = {
                    "uvs": [],
                    "pin_uvs": [],
                    "seams": [],
                    "face_indices": [],
                }
                info["uvs"] = [l[uv_layer].uv.copy() for l in face.loops]
                info["pin_uvs"] = [l[uv_layer].pin_uv for l in face.loops]
                info["seams"] = [l.edge.seam for l in face.loops]
                info["face_indices"] = face.index
                dest_info.append(info)
        if not dest_info:
            self.report({'WARNING'}, "No faces are selected")
            return {'CANCELLED'}
        if self.strategy == 'N_N' and len(props.src_uvs) != len(dest_uvs):
            self.report(
                {'WARNING'},
                "Number of selected faces is different from copied" +
                "(src:%d, dest:%d)" %
                (len(props.src_uvs), len(dest_uvs)))
            return {'CANCELLED'}

        # paste
        for i, idx in enumerate(dest_face_indices):
            suv = None
            spuv = None
            ss = None
            duv = None
            if self.strategy == 'N_N':
                suv = props.src_uvs[i]
                spuv = props.src_pin_uvs[i]
                ss = props.src_seams[i]
                duv = dest_uvs[i]
            elif self.strategy == 'N_M':
                suv = props.src_uvs[i % len(props.src_uvs)]
                spuv = props.src_pin_uvs[i % len(props.src_pin_uvs)]
                ss = props.src_seams[i % len(props.src_seams)]
                duv = dest_uvs[i]
            if len(suv) != len(duv):
                self.report({'WARNING'}, "Some faces are different size")
                return {'CANCELLED'}
            suvs_fr = [uv for uv in suv]
            spuvs_fr = [pin_uv for pin_uv in spuv]
            ss_fr = [s for s in ss]
            # flip UVs
            if self.flip_copied_uv is True:
                suvs_fr.reverse()
                spuvs_fr.reverse()
                ss_fr.reverse()
            # rotate UVs
            for _ in range(self.rotate_copied_uv):
                uv = suvs_fr.pop()
                pin_uv = spuvs_fr.pop()
                s = ss_fr.pop()
                suvs_fr.insert(0, uv)
                spuvs_fr.insert(0, pin_uv)
                ss_fr.insert(0, s)
            # paste UVs
            for l, suv, spuv, ss in zip(bm.faces[idx].loops, suvs_fr,
                                        spuvs_fr, ss_fr):
                l[uv_layer].uv = suv
                l[uv_layer].pin_uv = spuv
                if self.copy_seams is True:
                    l.edge.seam = ss
        self.report({'INFO'}, "%d face(s) are copied" % len(dest_uvs))

        bmesh.update_edit_mesh(obj.data)
        if self.copy_seams is True:
            obj.data.show_edge_seams = True

        return {'FINISHED'}


class MUV_CPUVPasteUVMenu(bpy.types.Menu):
    """
    Menu class: Paste UV coordinate
    """

    bl_idname = "uv.muv_cpuv_paste_uv_menu"
    bl_label = "Paste UV (Menu)"
    bl_description = "Menu of Paste UV coordinate"

    @classmethod
    def poll(cls, context):
        sc = context.scene
        props = sc.muv_props.cpuv
        if not props.src_uvs or not props.src_pin_uvs:
            return False
        return is_valid_context(context)

    def draw(self, context):
        sc = context.scene
        layout = self.layout
        # create sub menu
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        uv_maps = bm.loops.layers.uv.keys()

        ops = layout.operator(MUV_CPUVPasteUV.bl_idname, text="[Default]")
        ops.uv_map = "__default"
        ops.copy_seams = sc.muv_cpuv_copy_seams
        ops.strategy = sc.muv_cpuv_strategy

        ops = layout.operator(MUV_CPUVPasteUV.bl_idname, text="[New]")
        ops.uv_map = "__new"
        ops.copy_seams = sc.muv_cpuv_copy_seams
        ops.strategy = sc.muv_cpuv_strategy

        ops = layout.operator(MUV_CPUVPasteUV.bl_idname, text="[All]")
        ops.uv_map = "__all"
        ops.copy_seams = sc.muv_cpuv_copy_seams
        ops.strategy = sc.muv_cpuv_strategy

        for m in uv_maps:
            ops = layout.operator(MUV_CPUVPasteUV.bl_idname, text=m)
            ops.uv_map = m
            ops.copy_seams = sc.muv_cpuv_copy_seams
            ops.strategy = sc.muv_cpuv_strategy


class MUV_CPUVSelSeqCopyUV(bpy.types.Operator):
    """
    Operation class: Copy UV coordinate by selection sequence
    """

    bl_idname = "uv.muv_cpuv_selseq_copy_uv"
    bl_label = "Copy UV (Selection Sequence)"
    bl_description = "Copy UV data by selection sequence"
    bl_options = {'REGISTER', 'UNDO'}

    uv_map = StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return is_valid_context(context)

    def execute(self, context):
        props = context.scene.muv_props.cpuv_selseq
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        if common.check_version(2, 73, 0) >= 0:
            bm.faces.ensure_lookup_table()

        # get UV layer
        if self.uv_map == "__default":
            if not bm.loops.layers.uv:
                self.report(
                    {'WARNING'}, "Object must have more than one UV map")
                return {'CANCELLED'}
            uv_layer = bm.loops.layers.uv.verify()
            self.report({'INFO'}, "Copy UV coordinate (selection sequence)")
        else:
            uv_layer = bm.loops.layers.uv[self.uv_map]
            self.report(
                {'INFO'},
                "Copy UV coordinate (selection sequence) (UV map:%s)"
                % (self.uv_map))

        # get selected face
        props.src_uvs = []
        props.src_pin_uvs = []
        props.src_seams = []
        for hist in bm.select_history:
            if isinstance(hist, bmesh.types.BMFace) and hist.select:
                uvs = [l[uv_layer].uv.copy() for l in hist.loops]
                pin_uvs = [l[uv_layer].pin_uv for l in hist.loops]
                seams = [l.edge.seam for l in hist.loops]
                props.src_uvs.append(uvs)
                props.src_pin_uvs.append(pin_uvs)
                props.src_seams.append(seams)
        if not props.src_uvs or not props.src_pin_uvs:
            self.report({'WARNING'}, "No faces are selected")
            return {'CANCELLED'}
        self.report({'INFO'}, "%d face(s) are selected" % len(props.src_uvs))

        return {'FINISHED'}


class MUV_CPUVSelSeqCopyUVMenu(bpy.types.Menu):
    """
    Menu class: Copy UV coordinate by selection sequence
    """

    bl_idname = "uv.muv_cpuv_selseq_copy_uv_menu"
    bl_label = "Copy UV (Selection Sequence) (Menu)"
    bl_description = "Menu of Copy UV coordinate by selection sequence"

    @classmethod
    def poll(cls, context):
        return is_valid_context(context)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        uv_maps = bm.loops.layers.uv.keys()

        ops = layout.operator(MUV_CPUVSelSeqCopyUV.bl_idname, text="[Default]")
        ops.uv_map = "__default"

        for m in uv_maps:
            ops = layout.operator(MUV_CPUVSelSeqCopyUV.bl_idname, text=m)
            ops.uv_map = m


class MUV_CPUVSelSeqPasteUV(bpy.types.Operator):
    """
    Operation class: Paste UV coordinate by selection sequence
    """

    bl_idname = "uv.muv_cpuv_selseq_paste_uv"
    bl_label = "Paste UV (Selection Sequence)"
    bl_description = "Paste UV coordinate by selection sequence"
    bl_options = {'REGISTER', 'UNDO'}

    uv_map = StringProperty(options={'HIDDEN'})
    strategy = EnumProperty(
        name="Strategy",
        description="Paste Strategy",
        items=[
            ('N_N', 'N:N', 'Number of faces must be equal to source'),
            ('N_M', 'N:M', 'Number of faces must not be equal to source')
        ],
        default="N_M"
    )
    flip_copied_uv = BoolProperty(
        name="Flip Copied UV",
        description="Flip Copied UV...",
        default=False
    )
    rotate_copied_uv = IntProperty(
        default=0,
        name="Rotate Copied UV",
        min=0,
        max=30
    )
    copy_seams = BoolProperty(
        name="Copy Seams",
        description="Copy Seams",
        default=True
    )

    @classmethod
    def poll(cls, context):
        sc = context.scene
        props = sc.muv_props.cpuv_selseq
        if not props.src_uvs or not props.src_pin_uvs:
            return False
        return is_valid_context(context)

    def execute(self, context):
        props = context.scene.muv_props.cpuv_selseq
        if not props.src_uvs or not props.src_pin_uvs:
            self.report({'WARNING'}, "Need copy UV at first")
            return {'CANCELLED'}

        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        if common.check_version(2, 73, 0) >= 0:
            bm.faces.ensure_lookup_table()

        # get UV layer
        if self.uv_map == "__default":
            if not bm.loops.layers.uv:
                self.report(
                    {'WARNING'}, "Object must have more than one UV map")
                return {'CANCELLED'}
            uv_layer = bm.loops.layers.uv.verify()
            self.report({'INFO'}, "Paste UV coordinate (selection sequence)")
        elif self.uv_map == "__new":
            uv_maps_old = {l.name for l in obj.data.uv_layers}
            bpy.ops.mesh.uv_texture_add()
            uv_maps_new = {l.name for l in obj.data.uv_layers}
            diff = uv_maps_new - uv_maps_old
            bm = bmesh.from_edit_mesh(obj.data)
            if common.check_version(2, 73, 0) >= 0:
                bm.faces.ensure_lookup_table()
            uv_layer = bm.loops.layers.uv[list(diff)[0]]
            self.report(
                {'INFO'}, "Paste UV coordinate (UV map:%s)" % (list(diff)[0]))
        else:
            uv_layer = bm.loops.layers.uv[self.uv_map]
            self.report(
                {'INFO'},
                "Paste UV coordinate (selection sequence) (UV map:%s)"
                % (self.uv_map))

        # get selected face
        dest_uvs = []
        dest_pin_uvs = []
        dest_seams = []
        dest_face_indices = []
        for hist in bm.select_history:
            if isinstance(hist, bmesh.types.BMFace) and hist.select:
                dest_face_indices.append(hist.index)
                uvs = [l[uv_layer].uv.copy() for l in hist.loops]
                pin_uvs = [l[uv_layer].pin_uv for l in hist.loops]
                seams = [l.edge.seam for l in hist.loops]
                dest_uvs.append(uvs)
                dest_pin_uvs.append(pin_uvs)
                dest_seams.append(seams)
        if not dest_uvs or not dest_pin_uvs:
            self.report({'WARNING'}, "No faces are selected")
            return {'CANCELLED'}
        if self.strategy == 'N_N' and len(props.src_uvs) != len(dest_uvs):
            self.report(
                {'WARNING'},
                "Number of selected faces is different from copied faces " +
                "(src:%d, dest:%d)"
                % (len(props.src_uvs), len(dest_uvs)))
            return {'CANCELLED'}

        # paste
        for i, idx in enumerate(dest_face_indices):
            suv = None
            spuv = None
            ss = None
            duv = None
            if self.strategy == 'N_N':
                suv = props.src_uvs[i]
                spuv = props.src_pin_uvs[i]
                ss = props.src_seams[i]
                duv = dest_uvs[i]
            elif self.strategy == 'N_M':
                suv = props.src_uvs[i % len(props.src_uvs)]
                spuv = props.src_pin_uvs[i % len(props.src_pin_uvs)]
                ss = props.src_seams[i % len(props.src_seams)]
                duv = dest_uvs[i]
            if len(suv) != len(duv):
                self.report({'WARNING'}, "Some faces are different size")
                return {'CANCELLED'}
            suvs_fr = [uv for uv in suv]
            spuvs_fr = [pin_uv for pin_uv in spuv]
            ss_fr = [s for s in ss]
            # flip UVs
            if self.flip_copied_uv is True:
                suvs_fr.reverse()
                spuvs_fr.reverse()
                ss_fr.reverse()
            # rotate UVs
            for _ in range(self.rotate_copied_uv):
                uv = suvs_fr.pop()
                pin_uv = spuvs_fr.pop()
                s = ss_fr.pop()
                suvs_fr.insert(0, uv)
                spuvs_fr.insert(0, pin_uv)
                ss_fr.insert(0, s)
            # paste UVs
            for l, suv, spuv, ss in zip(bm.faces[idx].loops, suvs_fr,
                                        spuvs_fr, ss_fr):
                l[uv_layer].uv = suv
                l[uv_layer].pin_uv = spuv
                if self.copy_seams is True:
                    l.edge.seam = ss

        self.report({'INFO'}, "%d face(s) are copied" % len(dest_uvs))

        bmesh.update_edit_mesh(obj.data)
        if self.copy_seams is True:
            obj.data.show_edge_seams = True

        return {'FINISHED'}


class MUV_CPUVSelSeqPasteUVMenu(bpy.types.Menu):
    """
    Menu class: Paste UV coordinate by selection sequence
    """

    bl_idname = "uv.muv_cpuv_selseq_paste_uv_menu"
    bl_label = "Paste UV (Selection Sequence) (Menu)"
    bl_description = "Menu of Paste UV coordinate by selection sequence"

    @classmethod
    def poll(cls, context):
        sc = context.scene
        props = sc.muv_props.cpuv_selseq
        if not props.src_uvs or not props.src_pin_uvs:
            return False
        return is_valid_context(context)

    def draw(self, context):
        sc = context.scene
        layout = self.layout
        # create sub menu
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        uv_maps = bm.loops.layers.uv.keys()

        ops = layout.operator(MUV_CPUVSelSeqPasteUV.bl_idname, text="[Default]")
        ops.uv_map = "__default"
        ops.copy_seams = sc.muv_cpuv_copy_seams
        ops.strategy = sc.muv_cpuv_strategy

        ops = layout.operator(MUV_CPUVSelSeqPasteUV.bl_idname, text="[New]")
        ops.uv_map = "__new"
        ops.copy_seams = sc.muv_cpuv_copy_seams
        ops.strategy = sc.muv_cpuv_strategy

        for m in uv_maps:
            ops = layout.operator(MUV_CPUVSelSeqPasteUV.bl_idname, text=m)
            ops.uv_map = m
            ops.copy_seams = sc.muv_cpuv_copy_seams
            ops.strategy = sc.muv_cpuv_strategy
