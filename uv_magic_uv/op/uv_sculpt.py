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

from math import pi, cos, tan, sin

import bpy
import bmesh
import bgl
from mathutils import Vector
from bpy_extras import view3d_utils
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

from .. import common


__all__ = [
    'MUV_UVSculpt',
    'MUV_UVSculptEnable',
    'MUV_UVSculptDisable',
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


class MUV_UVSculpt(bpy.types.Operator):
    """
    Operation class: UV Sculpt in View3D
    """

    bl_idname = "uv.muv_uvsculpt"
    bl_label = "UV Sculpt"
    bl_description = "UV Sculpt in View3D"
    bl_options = {'REGISTER'}

    __handle = None
    __timer = None

    @classmethod
    def poll(cls, context):
        return is_valid_context(context)

    @classmethod
    def is_running(cls, _):
        return cls.__handle

    @classmethod
    def handle_add(cls, obj, context):
        if not cls.__handle:
            sv = bpy.types.SpaceView3D
            cls.__handle = sv.draw_handler_add(cls.draw_brush, (obj, context),
                                               "WINDOW", "POST_PIXEL")
        if not cls.__timer:
            cls.__timer = context.window_manager.event_timer_add(
                0.1, context.window)
            context.window_manager.modal_handler_add(obj)

    @classmethod
    def handle_remove(cls, context):
        if cls.__handle:
            sv = bpy.types.SpaceView3D
            sv.draw_handler_remove(cls.__handle, "WINDOW")
            cls.__handle = None
        if cls.__timer:
            context.window_manager.event_timer_remove(cls.__timer)
            cls.__timer = None

    @classmethod
    def draw_brush(cls, obj, context):
        sc = context.scene
        prefs = context.user_preferences.addons["uv_magic_uv"].preferences

        num_segment = 180
        theta = 2 * pi / num_segment
        fact_t = tan(theta)
        fact_r = cos(theta)
        color = prefs.uvsculpt_brush_color

        bgl.glBegin(bgl.GL_LINE_STRIP)
        bgl.glColor4f(color[0], color[1], color[2], color[3])
        x = sc.muv_uvsculpt_radius * cos(0.0)
        y = sc.muv_uvsculpt_radius * sin(0.0)
        for _ in range(num_segment):
            bgl.glVertex2f(x + obj.current_mco.x, y + obj.current_mco.y)
            tx = -y
            ty = x
            x = x + tx * fact_t
            y = y + ty * fact_t
            x = x * fact_r
            y = y * fact_r
        bgl.glEnd()

    def __init__(self):
        self.__loop_info = []
        self.__stroking = False
        self.current_mco = Vector((0.0, 0.0))
        self.__initial_mco = Vector((0.0, 0.0))

    def __get_strength(self, p, len_, factor):
        f = factor

        if p > len_:
            return 0.0

        if p < 0.0:
            return f

        return (len_ - p) * f / len_

    def __stroke_init(self, context, _):
        sc = context.scene

        self.__initial_mco = self.current_mco

        # get influenced UV
        obj = context.active_object
        world_mat = obj.matrix_world
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()
        _, region, space = common.get_space('VIEW_3D', 'WINDOW', 'VIEW_3D')

        self.__loop_info = []
        for f in bm.faces:
            if not f.select:
                continue
            for i, l in enumerate(f.loops):
                loc_2d = view3d_utils.location_3d_to_region_2d(
                    region, space.region_3d, world_mat * l.vert.co)
                diff = loc_2d - self.__initial_mco
                if diff.length < sc.muv_uvsculpt_radius:
                    info = {
                        "face_idx": f.index,
                        "loop_idx": i,
                        "initial_vco": l.vert.co.copy(),
                        "initial_vco_2d": loc_2d,
                        "initial_uv": l[uv_layer].uv.copy(),
                        "strength": self.__get_strength(
                            diff.length, sc.muv_uvsculpt_radius,
                            sc.muv_uvsculpt_strength)
                    }
                    self.__loop_info.append(info)

    def __stroke_apply(self, context, _):
        sc = context.scene
        obj = context.active_object
        world_mat = obj.matrix_world
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()
        mco = self.current_mco

        if sc.muv_uvsculpt_tools == 'GRAB':
            for info in self.__loop_info:
                diff_uv = (mco - self.__initial_mco) * info["strength"]
                l = bm.faces[info["face_idx"]].loops[info["loop_idx"]]
                l[uv_layer].uv = info["initial_uv"] + diff_uv / 100.0

        elif sc.muv_uvsculpt_tools == 'PINCH':
            _, region, space = common.get_space('VIEW_3D', 'WINDOW', 'VIEW_3D')
            loop_info = []
            for f in bm.faces:
                if not f.select:
                    continue
                for i, l in enumerate(f.loops):
                    loc_2d = view3d_utils.location_3d_to_region_2d(
                        region, space.region_3d, world_mat * l.vert.co)
                    diff = loc_2d - self.__initial_mco
                    if diff.length < sc.muv_uvsculpt_radius:
                        info = {
                            "face_idx": f.index,
                            "loop_idx": i,
                            "initial_vco": l.vert.co.copy(),
                            "initial_vco_2d": loc_2d,
                            "initial_uv": l[uv_layer].uv.copy(),
                            "strength": self.__get_strength(
                                diff.length, sc.muv_uvsculpt_radius,
                                sc.muv_uvsculpt_strength)
                        }
                        loop_info.append(info)

            # mouse coordinate to UV coordinate
            ray_vec = view3d_utils.region_2d_to_vector_3d(region,
                                                          space.region_3d, mco)
            ray_vec.normalize()
            ray_orig = view3d_utils.region_2d_to_origin_3d(region,
                                                           space.region_3d,
                                                           mco)
            ray_tgt = ray_orig + ray_vec * 1000000.0
            mwi = world_mat.inverted()
            ray_orig_obj = mwi * ray_orig
            ray_tgt_obj = mwi * ray_tgt
            ray_dir_obj = ray_tgt_obj - ray_orig_obj
            ray_dir_obj.normalize()
            tree = BVHTree.FromBMesh(bm)
            loc, _, fidx, _ = tree.ray_cast(ray_orig_obj, ray_dir_obj)
            if not loc:
                return
            loops = [l for l in bm.faces[fidx].loops]
            uvs = [Vector((l[uv_layer].uv.x, l[uv_layer].uv.y, 0.0))
                   for l in loops]
            target_uv = barycentric_transform(
                loc, loops[0].vert.co, loops[1].vert.co, loops[2].vert.co,
                uvs[0], uvs[1], uvs[2])
            target_uv = Vector((target_uv.x, target_uv.y))

            # move to target UV coordinate
            for info in loop_info:
                l = bm.faces[info["face_idx"]].loops[info["loop_idx"]]
                if sc.muv_uvsculpt_pinch_invert:
                    diff_uv = (l[uv_layer].uv - target_uv) * info["strength"]
                else:
                    diff_uv = (target_uv - l[uv_layer].uv) * info["strength"]
                l[uv_layer].uv = l[uv_layer].uv + diff_uv / 10.0

        elif sc.muv_uvsculpt_tools == 'RELAX':
            _, region, space = common.get_space('VIEW_3D', 'WINDOW', 'VIEW_3D')

            # get vertex and loop relation
            vert_db = {}
            for f in bm.faces:
                for l in f.loops:
                    if l.vert in vert_db:
                        vert_db[l.vert]["loops"].append(l)
                    else:
                        vert_db[l.vert] = {"loops": [l]}

            # get relaxation information
            for k in vert_db.keys():
                d = vert_db[k]
                d["uv_sum"] = Vector((0.0, 0.0))
                d["uv_count"] = 0

                for l in d["loops"]:
                    ln = l.link_loop_next
                    lp = l.link_loop_prev
                    d["uv_sum"] = d["uv_sum"] + ln[uv_layer].uv
                    d["uv_sum"] = d["uv_sum"] + lp[uv_layer].uv
                    d["uv_count"] = d["uv_count"] + 2
                d["uv_p"] = d["uv_sum"] / d["uv_count"]
                d["uv_b"] = d["uv_p"] - d["loops"][0][uv_layer].uv
            for k in vert_db.keys():
                d = vert_db[k]
                d["uv_sum_b"] = Vector((0.0, 0.0))
                for l in d["loops"]:
                    ln = l.link_loop_next
                    lp = l.link_loop_prev
                    dn = vert_db[ln.vert]
                    dp = vert_db[lp.vert]
                    d["uv_sum_b"] = d["uv_sum_b"] + dn["uv_b"] + dp["uv_b"]

            # apply
            for f in bm.faces:
                if not f.select:
                    continue
                for i, l in enumerate(f.loops):
                    loc_2d = view3d_utils.location_3d_to_region_2d(
                        region, space.region_3d, world_mat * l.vert.co)
                    diff = loc_2d - self.__initial_mco
                    if diff.length >= sc.muv_uvsculpt_radius:
                        continue
                    db = vert_db[l.vert]
                    strength = self.__get_strength(diff.length,
                                                   sc.muv_uvsculpt_radius,
                                                   sc.muv_uvsculpt_strength)

                    base = (1.0 - strength) * l[uv_layer].uv
                    if sc.muv_uvsculpt_relax_method == 'HC':
                        t = 0.5 * (db["uv_b"] + db["uv_sum_b"] / d["uv_count"])
                        diff = strength * (db["uv_p"] - t)
                        target_uv = base + diff
                    elif sc.muv_uvsculpt_relax_method == 'LAPLACIAN':
                        diff = strength * db["uv_p"]
                        target_uv = base + diff
                    else:
                        continue

                    l[uv_layer].uv = target_uv

        bmesh.update_edit_mesh(obj.data)

    def __stroke_exit(self, context, _):
        sc = context.scene
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()
        mco = self.current_mco

        if sc.muv_uvsculpt_tools == 'GRAB':
            for info in self.__loop_info:
                diff_uv = (mco - self.__initial_mco) * info["strength"]
                l = bm.faces[info["face_idx"]].loops[info["loop_idx"]]
                l[uv_layer].uv = info["initial_uv"] + diff_uv / 100.0

        bmesh.update_edit_mesh(obj.data)

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()


        if not MUV_UVSculpt.is_running(context):
            MUV_UVSculpt.handle_remove()

            return {'FINISHED'}

        self.current_mco = Vector((event.mouse_region_x, event.mouse_region_y))
        area, _, _ = common.get_space('VIEW_3D', 'WINDOW', 'VIEW_3D')

        if self.current_mco.x < 0 or self.current_mco.x > area.width or \
           self.current_mco.y < 0 or self.current_mco.y > area.height:
            return {'PASS_THROUGH'}

        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                if not self.__stroking:
                    self.__stroke_init(context, event)
                self.__stroking = True
            elif event.value == 'RELEASE':
                if self.__stroking:
                    self.__stroke_exit(context, event)
                self.__stroking = False
        elif event.type == 'MOUSEMOVE':
            if self.__stroking:
                self.__stroke_apply(context, event)
        elif event.type == 'TIMER':
            if self.__stroking:
                self.__stroke_apply(context, event)

        return {'RUNNING_MODAL'}

    def execute(self, context):
        if context.area:
            context.area.tag_redraw()

        if MUV_UVSculpt.is_running(context):
            MUV_UVSculpt.handle_remove(context)
        else:
            MUV_UVSculpt.handle_add(context)


        return {'RUNNING_MODAL'}


class MUV_UVSculptEnable(bpy.types.Operator):
    """
    Operation class: Enable
    """

    bl_idname = "uv.muv_uvsculpt_enable"
    bl_label = "Enable UV Sculpt"
    bl_description = "Enable UV Sculpt"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if MUV_UVSculpt.is_running(context):
            return False
        return is_valid_context(context)

    def execute(self, context):
        if MUV_UVSculpt.is_running(context):
            return {'CANCELLED'}

        bpy.ops.uv.muv_uvsculpt()

        return {'FINISHED'}


class MUV_UVSculptDisable(bpy.types.Operator):
    """
    Operation class: Disable
    """

    bl_idname = "uv.muv_uvsculpt_disable"
    bl_label = "Disable UV Sculpt"
    bl_description = "Disable UV Sculpt"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not MUV_UVSculpt.is_running(context):
            return False
        return is_valid_context(context)

    def execute(self, context):
        if not MUV_UVSculpt.is_running(context):
            return {'CANCELLED'}

        bpy.ops.uv.muv_uvsculpt()

        return {'FINISHED'}
