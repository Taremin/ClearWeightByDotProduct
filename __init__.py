import bpy
import bmesh
import gpu
from gpu_extras.batch import batch_for_shader
import hashlib
import colorsys
from mathutils import Vector


# アドオン情報
bl_info = {
    "name": "Clear Weight by Dot Product",
    "category": "Tools",
    "author": "Taremin",
    "location": "View 3D > UI > Taremin",
    "description": "",
    "version": (0, 0, 2),
    "blender": (4, 0, 0),
    "wiki_url": "",
    "tracker_url": "",
    "warning": "",
}


def update_highlight(self, context):
    """プロパティ変更時に 3D ビューを再描画"""
    if context.area:
        context.area.tag_redraw()


def update_precomputation_and_redraw(self, context):
    """前計算データを更新し、3Dビューを再描画"""
    # updateコールバックのselfはbpy_structなため、invoke時に保存した
    # クラスインスタンス経由でメソッドを呼び出す必要があります。
    op_instance = (
        OBJECT_OT_TareminBoneWeightTools_ClearWeightByDotProduct._active_instance
    )
    if op_instance:
        op_instance.precompute_data(context)
        update_highlight(self, context)


def bone_name_to_color(name):
    """ボーン名から安定したユニークな色を生成します。"""
    hash_obj = hashlib.md5(name.encode())
    hash_digest = hash_obj.hexdigest()
    hue = int(hash_digest, 16) % 360 / 360.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.9, 1.0)
    return (r, g, b, 1.0)


class OBJECT_OT_TareminBoneWeightTools_ClearWeightByDotProduct(bpy.types.Operator):
    bl_idname = "taremin.bone_weight_tools_clear_weight_by_dot_product"
    bl_label = "Clear Weight by Dot Product"
    bl_options = {"REGISTER"}

    def get_preview_objects(self, context):
        """クラス変数に保持されているEnumPropertyのアイテムリストを返す"""
        cls = OBJECT_OT_TareminBoneWeightTools_ClearWeightByDotProduct
        return cls._enum_items

    preview_object: bpy.props.EnumProperty(
        name="Preview Object",
        items=get_preview_objects,
        update=update_highlight,  # 再計算は不要で再描画のみ行う
    )
    bonetype: bpy.props.EnumProperty(
        name="BoneType",
        items=[("BONE", "Bone", ""), ("POSE", "PoseBone", "")],
        default="POSE",
        update=update_precomputation_and_redraw,
    )
    dot_threshold: bpy.props.FloatProperty(
        name="Threshold",
        default=0.0,
        min=-1.0,
        max=1.0,
        update=update_precomputation_and_redraw,
    )
    selected_vertex_only: bpy.props.BoolProperty(
        name="Selected Vertices Only",
        default=False,
        update=update_precomputation_and_redraw,
    )
    selected_bone_only: bpy.props.BoolProperty(
        name="Selected Bones Only",
        default=False,
        update=update_precomputation_and_redraw,
    )
    remove: bpy.props.BoolProperty(
        name="Remove vertex group that are no longer needed from vertices",
        default=False,
        update=update_precomputation_and_redraw,
    )
    offset: bpy.props.FloatProperty(
        name="Offset", default=0.0, update=update_precomputation_and_redraw
    )

    _handler = None
    _precomputed_cache = {}
    _original_shading_type = None
    _selectable_objects = []
    _enum_items = []
    _active_instance = None

    def invoke(self, context, event):
        # このオペレータのインスタンスをクラス変数に保存
        type(self)._active_instance = self
        selected_meshes = [
            obj for obj in context.selected_objects if obj.type == "MESH"
        ]
        if not selected_meshes:
            self.report({"WARNING"}, "No mesh objects selected for preview.")
            return {"CANCELLED"}

        # アクティブオブジェクトをリストの先頭に配置
        active_obj = context.active_object
        if active_obj and active_obj in selected_meshes:
            selected_meshes.insert(
                0, selected_meshes.pop(selected_meshes.index(active_obj))
            )

        type(self)._selectable_objects = selected_meshes

        # EnumPropertyのアイテムリストをクラス変数に保持し、GCによる文字化けを防ぐ
        items = []
        for i, obj in enumerate(selected_meshes):
            items.append((str(i), obj.name, f"Preview {obj.name}"))
        if not items:
            items.append(("0", "No Mesh Selected", ""))
        type(self)._enum_items = items
        # self.preview_objectはデフォルト値("0")のままにし、
        # リストの先頭（アクティブオブジェクト）が自動選択されるようにする

        # 元のシェーディングを保存し、プレビュー用にワイヤーフレームに設定
        if context.space_data.type == "VIEW_3D":
            self._original_shading_type = context.space_data.shading.type
            context.space_data.shading.type = "WIREFRAME"

        self.precompute_data(context)

        args = (self, context)
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback, args, "WINDOW", "POST_VIEW"
        )
        if context.area:
            context.area.tag_redraw()
        return context.window_manager.invoke_props_dialog(self)

    def finish(self, context):
        """オペレータ終了時の後片付け"""
        if context.space_data.type == "VIEW_3D" and self._original_shading_type:
            context.space_data.shading.type = self._original_shading_type
            self._original_shading_type = None

        if self._handler:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, "WINDOW")
            self._handler = None
        # 他の操作に影響が出ないよう、クラス変数をクリーンアップ
        type(self)._active_instance = None
        type(self)._enum_items = []
        type(self)._selectable_objects = []
        type(self)._precomputed_cache.clear()
        if context.area:
            context.area.tag_redraw()

    def cancel(self, context):
        self.finish(context)
        return {"CANCELLED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "preview_object")
        layout.prop(self, "bonetype")
        layout.prop(self, "dot_threshold")
        layout.prop(self, "offset")
        layout.prop(self, "selected_vertex_only")
        layout.prop(self, "selected_bone_only")
        layout.prop(self, "remove")

    def _compute_data_for_object(self, obj):
        """指定されたオブジェクトの計算に必要なデータを収集して返す"""
        if not obj or obj.type != "MESH":
            return None

        armature = obj.find_armature()
        if not armature:
            return None

        computed_data = {"verts": {}, "bones": []}
        matrix_world = obj.matrix_world
        arm_matrix_world = armature.matrix_world

        # ボーンデータを前計算
        bones_to_check = armature.data.bones
        if self.selected_bone_only:
            bones_to_check = [b for b in armature.data.bones if b.select]

        vg_indices = {vg.name: vg.index for vg in obj.vertex_groups}

        for bone in bones_to_check:
            if self.bonetype == "POSE":
                pbone = armature.pose.bones.get(bone.name)
                if not pbone:
                    continue
                head = arm_matrix_world @ pbone.head
                tail = arm_matrix_world @ pbone.tail
            else:  # BONE
                head = arm_matrix_world @ bone.head_local
                tail = arm_matrix_world @ bone.tail_local

            computed_data["bones"].append(
                {
                    "name": bone.name,
                    "head": head,
                    "tail": tail,
                    "vector": (tail - head).normalized(),
                    "color": bone_name_to_color(bone.name),
                    "vg_index": vg_indices.get(bone.name),
                }
            )

        # 頂点データを前計算 (BMeshを使用して高速化)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        deform_layer = bm.verts.layers.deform.active

        target_vert_indices = {v.index for v in bm.verts}
        if self.selected_vertex_only:
            target_vert_indices = {v.index for v in bm.verts if v.select}

        if deform_layer:
            for v in bm.verts:
                if v.index in target_vert_indices:
                    weights = {
                        vg_idx: weight
                        for vg_idx, weight in v[deform_layer].items()
                        if weight > 0
                    }
                    if weights:
                        computed_data["verts"][v.index] = {
                            "co": matrix_world @ v.co,
                            "weights": weights,
                        }
        bm.free()
        return computed_data

    def precompute_data(self, context):
        cls = type(self)
        cls._precomputed_cache.clear()
        for obj in cls._selectable_objects:
            computed_data = self._compute_data_for_object(obj)
            cls._precomputed_cache[obj.name] = computed_data

    def _calculate_affecting_map(self, precomputed_data):
        """
        事前計算されたデータから、実際に影響を受ける頂点のマップを計算する。
        このメソッドはプレビューと実行の両方から呼び出される共通ロジック。
        """
        if not precomputed_data:
            return {}

        affecting_map = {}
        bone_data = precomputed_data["bones"]
        verts_data = precomputed_data["verts"]

        for v_idx, vert_info in verts_data.items():
            vert_pos = vert_info["co"]
            vert_weights = vert_info["weights"]
            affecting_bones = []

            for bone in bone_data:
                if bone["vg_index"] not in vert_weights:
                    continue

                bone_vector = bone["vector"]
                head = bone["head"]
                vertex_vector = (
                    vert_pos - (head - bone_vector * self.offset)
                ).normalized()
                dot = bone_vector.dot(vertex_vector)

                if dot < self.dot_threshold:
                    affecting_bones.append(bone["name"])

            if affecting_bones:
                affecting_map[v_idx] = affecting_bones
        return affecting_map

    def get_affecting_data(self, preview_obj_name):
        """キャッシュされたデータを使用して、影響を受ける頂点と描画用データを計算する"""
        precomputed_data = type(self)._precomputed_cache.get(preview_obj_name)
        if not precomputed_data:
            return {}, {}

        # 共通ロジックを呼び出して影響マップを取得
        affecting_map = self._calculate_affecting_map(precomputed_data)

        # 実際に頂点に影響を与えているボーンの名前だけを収集
        active_bone_names = {
            bone_name for bone_list in affecting_map.values() for bone_name in bone_list
        }

        # 描画用のボーンデータを作成
        bone_coords = []
        bone_colors = []
        bone_data = precomputed_data["bones"]
        for bone in bone_data:
            if bone["name"] in active_bone_names:
                bone_coords.extend([bone["head"], bone["tail"]])
                bone_colors.extend([bone["color"], bone["color"]])

        bone_draw_data = {
            "coords": bone_coords,
            "colors": bone_colors,
            "color_map": {bone["name"]: bone["color"] for bone in bone_data},
        }

        return affecting_map, bone_draw_data

    def draw_callback(self, op, ctx):
        """ビューポートにハイライトを描画する"""
        # プレビュー対象として選択されているインデックスからオブジェクトを取得
        try:
            cls = type(self)
            obj_index = int(self.preview_object)
            obj = cls._selectable_objects[obj_index]
            preview_obj_name = obj.name
        except (ValueError, IndexError, AttributeError):
            return

        if not obj or not preview_obj_name:
            return

        armature = obj.find_armature()
        if not armature:
            return

        affecting_map, bone_draw_data = self.get_affecting_data(preview_obj_name)

        highlight_coords = []
        highlight_colors = []
        bone_color_map = bone_draw_data.get("color_map", {})

        for v_idx, affecting_bones in affecting_map.items():
            highlight_coords.append(obj.data.vertices[v_idx].co)
            if len(affecting_bones) > 1:
                # 複数のボーンから影響を受ける頂点は白でハイライト
                highlight_colors.append((1.0, 1.0, 1.0, 1.0))
            else:
                color = bone_color_map.get(affecting_bones[0], (1.0, 0.0, 1.0, 1.0))
                highlight_colors.append(color)

        # GPU描画
        shader = gpu.shader.from_builtin("SMOOTH_COLOR")
        gpu.state.point_size_set(5)
        batch_verts = batch_for_shader(
            shader, "POINTS", {"pos": highlight_coords, "color": highlight_colors}
        )
        batch_bones = batch_for_shader(
            shader,
            "LINES",
            {
                "pos": bone_draw_data.get("coords", []),
                "color": bone_draw_data.get("colors", []),
            },
        )

        shader.bind()
        batch_bones.draw(shader)
        batch_verts.draw(shader)

    def execute(self, context):
        if bpy.context.mode in ("OBJECT", "EDIT", "EDIT_MESH", "PAINT_WEIGHT"):
            for obj in bpy.context.selected_objects:
                self.execute_object(context, obj)

        self.finish(context)
        return {"FINISHED"}

    def execute_object(self, context, obj):
        precomputed_data = type(self)._precomputed_cache.get(obj.name)
        if not precomputed_data:
            return

        affecting_map = self._calculate_affecting_map(precomputed_data)
        if not affecting_map:
            return

        mesh = obj.data
        if obj.mode == "EDIT":
            bm = bmesh.from_edit_mesh(mesh)
        else:
            bm = bmesh.new()
            bm.from_mesh(mesh)

        bm.verts.ensure_lookup_table()
        layer_deform = bm.verts.layers.deform.active
        if layer_deform is None:
            bm.free()
            return

        vg_indices = {vg.name: vg.index for vg in obj.vertex_groups}

        for v_idx, bone_names in affecting_map.items():
            bmv = bm.verts[v_idx]
            for bone_name in bone_names:
                vg_index = vg_indices.get(bone_name)
                if vg_index is not None and vg_index in bmv[layer_deform]:
                    if self.remove:
                        del bmv[layer_deform][vg_index]
                    else:
                        bmv[layer_deform][vg_index] = 0.0

        if obj.mode == "EDIT":
            bmesh.update_edit_mesh(mesh)
        else:
            bm.to_mesh(mesh)
        bm.free()


def draw(self, context):
    self.layout.operator(
        OBJECT_OT_TareminBoneWeightTools_ClearWeightByDotProduct.bl_idname
    )


classes = [OBJECT_OT_TareminBoneWeightTools_ClearWeightByDotProduct]


def register():
    for value in classes:
        bpy.utils.register_class(value)
    bpy.types.VIEW3D_MT_edit_mesh_weights.append(draw)
    bpy.types.VIEW3D_MT_paint_weight.append(draw)


def unregister():
    bpy.types.VIEW3D_MT_edit_mesh_weights.remove(draw)
    bpy.types.VIEW3D_MT_paint_weight.remove(draw)
    for value in classes:
        bpy.utils.unregister_class(value)


if __name__ == "__main__":
    register()
