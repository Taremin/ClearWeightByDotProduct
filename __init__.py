import bpy
import bmesh

# アドオン情報
bl_info = {
    "name": "Clear Weight by Dot Product",
    "category": "Tools",
    "author": "Taremin",
    "location": "View 3D > UI > Taremin",
    "description": "",
    "version": (0, 0, 1),
    "blender": (2, 80, 0),
    "wiki_url": "",
    "tracker_url": "",
    "warning": "",
}


class OBJECT_OT_TareminBoneWeightTools_ClearWeightByDotProduct(bpy.types.Operator):
    bl_idname = "taremin.bone_weight_tools_multiply_weight_by_dot_product"
    bl_label = "Clear Weight by Dot Product"
    bl_options = {"REGISTER", "UNDO"}

    bonetype: bpy.props.EnumProperty(
        name="BoneType",
        items=[("BONE", "Bone", ""), ("POSE", "PoseBone", "")],
        default="POSE",
    )
    dot_threshold: bpy.props.FloatProperty(
        name="Threshold", default=0.0, min=-1.0, max=1.0
    )
    selected_vertex_only: bpy.props.BoolProperty(
        name="Selected Vertices Only", default=False
    )
    selected_bone_only: bpy.props.BoolProperty(
        name="Selected Bones Only", default=False
    )
    remove: bpy.props.BoolProperty(
        name="Remove vertex group that are no longer needed from vertices",
        default=False,
    )
    offset: bpy.props.FloatProperty(name="Offset", default=0.0)

    def execute(self, context):
        if bpy.context.mode == "OBJECT":
            for obj in bpy.context.selected_objects:
                self.execute_object(context, obj)
        elif bpy.context.mode == "EDIT":
            self.execute_object(context, bpy.context.active_object)
        elif bpy.context.mode == "PAINT_WEIGHT":
            self.execute_object(context, bpy.context.active_object)

        return {"FINISHED"}

    def execute_object(self, context, obj):
        mesh = obj.data
        if obj.mode == "EDIT":
            bm = bmesh.from_edit_mesh(mesh)
        else:
            bm = bmesh.new()
            bm.from_mesh(mesh)

        layer_deform = bm.verts.layers.deform.active

        if layer_deform is None:
            return {"CANCELLED"}

        armatures = []
        for mod in obj.modifiers:
            if mod.type != "ARMATURE":
                continue
            if mod.object is None:
                continue
            armatures.append(mod.object)

        if len(armatures) != 1:
            return {"CANCELLED"}

        bm.verts.ensure_lookup_table()
        names = tuple(vertex_group.name for vertex_group in obj.vertex_groups)
        matrix_world = obj.matrix_world

        verts = (
            [v for v in bm.verts if v.select] if self.selected_vertex_only else bm.verts
        )
        for bmv in verts:
            vert_pos = matrix_world @ bmv.co

            for vertex_group_index, weight in bmv[layer_deform].items():
                name = names[vertex_group_index]

                for armature in armatures:
                    matrix = armature.matrix_world

                    if self.bonetype == "POSE":
                        bone = armature.pose.bones.get(name)
                        if bone is None:
                            continue
                        head = matrix @ bone.head
                        tail = matrix @ bone.tail
                        select = bone.bone.select
                    else:
                        bone = armature.data.bones.get(name)
                        if bone is None:
                            continue
                        head = matrix @ bone.head_local
                        tail = matrix @ bone.tail_local
                        select = bone.select

                    if self.selected_bone_only and not select:
                        continue

                    bone_vector = tail - head
                    vertex_vector = vert_pos - (head - bone_vector * self.offset)
                    dot = bone_vector.dot(vertex_vector)

                    if dot < self.dot_threshold:
                        if self.remove:
                            del bmv[layer_deform][vertex_group_index]
                        else:
                            bmv[layer_deform][vertex_group_index] = 0

        if obj.mode == "EDIT":
            bmesh.update_edit_mesh(mesh)
        else:
            bm.to_mesh(mesh)
        bm.free()


def draw(self, context):
    self.layout.operator(
        OBJECT_OT_TareminBoneWeightTools_ClearWeightByDotProduct.bl_idname
    )


classes = [
    OBJECT_OT_TareminBoneWeightTools_ClearWeightByDotProduct,
]


def register():
    for value in classes:
        bpy.utils.register_class(value)
    bpy.types.VIEW3D_MT_edit_mesh_weights.append(draw)
    bpy.types.VIEW3D_MT_paint_weight.append(draw)
    # bpy.types.VIEW3D_MT_object_cleanup.append(draw)


def unregister():
    bpy.types.VIEW3D_MT_edit_mesh_weights.remove(draw)
    bpy.types.VIEW3D_MT_paint_weight.remove(draw)
    # bpy.types.VIEW3D_MT_object_cleanup.remove(draw)
    for value in classes:
        bpy.utils.unregister_class(value)


if __name__ == "__main__":
    register()
