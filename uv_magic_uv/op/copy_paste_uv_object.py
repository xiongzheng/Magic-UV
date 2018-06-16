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

__author__ = "Nutti <nutti.metro@gmail.com>"
__status__ = "production"
__version__ = "5.1"
__date__ = "24 Feb 2018"

import bpy
import bmesh
from bpy.props import (
    StringProperty,
    BoolProperty,
)

from .. import common


__all__ = [
    'MUV_CPUVObjCopyUV',
    'MUV_CPUVObjCopyUVMenu',
    'MUV_CPUVObjPasteUV',
    'MUV_CPUVObjPasteUVMenu',
]


def is_valid_context(context):
    obj = context.object

    # only object mode is allowed to execute
    if obj is None:
        return False
    if obj.type != 'MESH':
        return False
    if context.object.mode != 'OBJECT':
        return False

    # only 'VIEW_3D' space is allowed to execute
    for space in context.area.spaces:
        if space.type == 'VIEW_3D':
            break
    else:
        return False

    return True


def memorize_view_3d_mode(fn):
    def __memorize_view_3d_mode(self, context):
        mode_orig = bpy.context.object.mode
        result = fn(self, context)
        bpy.ops.object.mode_set(mode=mode_orig)
        return result
    return __memorize_view_3d_mode


class MUV_CPUVObjCopyUV(bpy.types.Operator):
    """
    Operation class: Copy UV coordinate among objects
    """

    bl_idname = "object.muv_cpuv_obj_copy_uv"
    bl_label = "Copy UV (Among Objects)"
    bl_description = "Copy UV coordinate (Among Objects)"
    bl_options = {'REGISTER', 'UNDO'}

    uv_map = StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return is_valid_context(context)

    @memorize_view_3d_mode
    def execute(self, context):
        props = context.scene.muv_props.cpuv_obj

        bpy.ops.object.mode_set(mode='EDIT')

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
            self.report({'INFO'}, "Copy UV coordinate per object")
        else:
            uv_layer = bm.loops.layers.uv[self.uv_map]
            self.report(
                {'INFO'},
                "Copy UV coordinate per object (UV map:%s)" % (self.uv_map))

        # get selected face
        props.src_uvs = []
        props.src_pin_uvs = []
        props.src_seams = []
        for face in bm.faces:
            uvs = [l[uv_layer].uv.copy() for l in face.loops]
            pin_uvs = [l[uv_layer].pin_uv for l in face.loops]
            seams = [l.edge.seam for l in face.loops]
            props.src_uvs.append(uvs)
            props.src_pin_uvs.append(pin_uvs)
            props.src_seams.append(seams)

        self.report({'INFO'}, "%s's UV coordinates are copied" % (obj.name))

        return {'FINISHED'}


class MUV_CPUVObjCopyUVMenu(bpy.types.Menu):
    """
    Menu class: Copy UV coordinate among objects
    """

    bl_idname = "object.muv_cpuv_obj_copy_uv_menu"
    bl_label = "Copy UV (Among Objects) (Menu)"
    bl_description = "Menu of Copy UV coordinate (Among Objects)"

    @classmethod
    def poll(cls, context):
        return is_valid_context(context)

    def draw(self, _):
        layout = self.layout
        # create sub menu
        uv_maps = bpy.context.active_object.data.uv_textures.keys()

        ops = layout.operator(MUV_CPUVObjCopyUV.bl_idname, text="[Default]")
        ops.uv_map = "__default"

        for m in uv_maps:
            ops = layout.operator(MUV_CPUVObjCopyUV.bl_idname, text=m)
            ops.uv_map = m


class MUV_CPUVObjPasteUV(bpy.types.Operator):
    """
    Operation class: Paste UV coordinate among objects
    """

    bl_idname = "object.muv_cpuv_obj_paste_uv"
    bl_label = "Paste UV (Among Objects)"
    bl_description = "Paste UV coordinate (Among Objects)"
    bl_options = {'REGISTER', 'UNDO'}

    uv_map = StringProperty(options={'HIDDEN'})
    copy_seams = BoolProperty(
        name="Copy Seams",
        description="Copy Seams",
        default=True
    )

    @classmethod
    def poll(cls, context):
        sc = context.scene
        props = sc.muv_props.cpuv_obj
        if not props.src_uvs or not props.src_pin_uvs:
            return False
        return is_valid_context(context)

    @memorize_view_3d_mode
    def execute(self, context):
        props = context.scene.muv_props.cpuv_obj
        if not props.src_uvs or not props.src_pin_uvs:
            self.report({'WARNING'}, "Need copy UV at first")
            return {'CANCELLED'}

        for o in bpy.data.objects:
            if not hasattr(o.data, "uv_textures") or not o.select:
                continue

            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.context.scene.objects.active = o
            bpy.ops.object.mode_set(mode='EDIT')

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
                self.report({'INFO'}, "Paste UV coordinate per object")
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
                    {'INFO'},
                    "Paste UV coordinate (UV map:%s)" % (list(diff)[0]))
            else:
                uv_layer = bm.loops.layers.uv[self.uv_map]
                self.report(
                    {'INFO'},
                    "Paste UV coordinate per object (UV map: %s)"
                    % (self.uv_map))

            # get selected face
            dest_uvs = []
            dest_pin_uvs = []
            dest_seams = []
            dest_face_indices = []
            for face in bm.faces:
                dest_face_indices.append(face.index)
                uvs = [l[uv_layer].uv.copy() for l in face.loops]
                pin_uvs = [l[uv_layer].pin_uv for l in face.loops]
                seams = [l.edge.seam for l in face.loops]
                dest_uvs.append(uvs)
                dest_pin_uvs.append(pin_uvs)
                dest_seams.append(seams)
            if len(props.src_uvs) != len(dest_uvs):
                self.report(
                    {'WARNING'},
                    "Number of faces is different from copied " +
                    "(src:%d, dest:%d)"
                    % (len(props.src_uvs), len(dest_uvs))
                )
                return {'CANCELLED'}

            # paste
            for i, idx in enumerate(dest_face_indices):
                suv = props.src_uvs[i]
                spuv = props.src_pin_uvs[i]
                ss = props.src_seams[i]
                duv = dest_uvs[i]
                if len(suv) != len(duv):
                    self.report({'WARNING'}, "Some faces are different size")
                    return {'CANCELLED'}
                suvs_fr = [uv for uv in suv]
                spuvs_fr = [pin_uv for pin_uv in spuv]
                ss_fr = [s for s in ss]
                # paste UVs
                for l, suv, spuv, ss in zip(
                        bm.faces[idx].loops, suvs_fr, spuvs_fr, ss_fr):
                    l[uv_layer].uv = suv
                    l[uv_layer].pin_uv = spuv
                    if self.copy_seams is True:
                        l.edge.seam = ss

            bmesh.update_edit_mesh(obj.data)
            if self.copy_seams is True:
                obj.data.show_edge_seams = True

            self.report(
                {'INFO'}, "%s's UV coordinates are pasted" % (obj.name))

        return {'FINISHED'}


class MUV_CPUVObjPasteUVMenu(bpy.types.Menu):
    """
    Menu class: Paste UV coordinate among objects
    """

    bl_idname = "object.muv_cpuv_obj_paste_uv_menu"
    bl_label = "Paste UV (Among Objects) (Menu)"
    bl_description = "Menu of Paste UV coordinate (Among Objects)"

    @classmethod
    def poll(cls, context):
        sc = context.scene
        props = sc.muv_props.cpuv_obj
        if not props.src_uvs or not props.src_pin_uvs:
            return False
        return is_valid_context(context)

    def draw(self, context):
        sc = context.scene
        layout = self.layout
        # create sub menu
        uv_maps = []
        for obj in bpy.data.objects:
            if hasattr(obj.data, "uv_textures") and obj.select:
                uv_maps.extend(obj.data.uv_textures.keys())

        ops = layout.operator(MUV_CPUVObjPasteUV.bl_idname, text="[Default]")
        ops.uv_map = "__default"
        ops.copy_seams = sc.muv_cpuv_copy_seams

        ops = layout.operator(MUV_CPUVObjPasteUV.bl_idname, text="[New]")
        ops.uv_map = "__new"
        ops.copy_seams = sc.muv_cpuv_copy_seams

        for m in uv_maps:
            ops = layout.operator(MUV_CPUVObjPasteUV.bl_idname, text=m)
            ops.uv_map = m
            ops.copy_seams = sc.muv_cpuv_copy_seams
