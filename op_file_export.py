import bpy, bmesh
import os
import mathutils
import math
import imp
import pathlib

from . import objects_organise

from . import modifiers
from . import platforms

imp.reload(modifiers)
imp.reload(platforms)


class op(bpy.types.Operator):
	bl_idname = "fbxbundle.file_export"
	bl_label = "export"
	bl_description = "Export selected bundles"

	@classmethod
	def poll(cls, context):

		if context.space_data.local_view:
			return False
		
		if len(bpy.context.selected_objects) == 0:
			return False

		if bpy.context.scene.FBXBundleSettings.path == "":
			return False

		if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
			return False

		if len( objects_organise.get_bundles() ) == 0:
			return False


		return True

	def execute(self, context):
		export(self, bpy.context.scene.FBXBundleSettings.target_platform, False)
		return {'FINISHED'}

class op_all(bpy.types.Operator):
	bl_idname = "fbxbundle.file_export_all"
	bl_label = "export_all"
	bl_description = "Export all bundles"

	@classmethod
	def poll(cls, context):

		if context.space_data.local_view:
			return False

		if bpy.context.scene.FBXBundleSettings.path == "":
			return False

		return True

	def execute(self, context):
		export(self, bpy.context.scene.FBXBundleSettings.target_platform, True)
		return {'FINISHED'}

prefix_copy = "EXPORT_ORG_"

def export_object(obj, prefix_copy, originals, copies, pivot):
	if obj in originals:
		return None

	if not obj.visible_get():
		return None

	children = []
	for child in obj.children:
		if not child.visible_get():
			continue

		output = export_object(child, prefix_copy, originals, copies, pivot)
		if output is not None:
			children.append(output)

	name_original = obj.name
	obj.name = prefix_copy+name_original

	bpy.ops.object.select_all(action="DESELECT")
	obj.select_set(state = True)

	bpy.context.view_layer.objects.active = obj
	obj.hide_viewport = False

	originals.append(bpy.context.object)
	
	# Copy
	copy = None

	if obj.type != 'EMPTY':
		bpy.ops.object.duplicate()
		copy = bpy.context.object

		bpy.ops.object.convert(target='MESH')

		for child in children:
			child.parent = copy

	else:
		if len(obj.children) == 0:
			return None

		bpy.ops.object.select_all(action="DESELECT")

		for child in children:
			bpy.context.view_layer.objects.active = child
			bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
			child.select_set(state = True)
			copies.remove(child)

		offset = obj.location
		if obj.parent is not None:
			offset = obj.location - obj.parent.location

		bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]

		bpy.ops.object.join()
		copy = bpy.context.object
		# copy.location += obj.location
		# copy.rotation_euler.rotate(obj.rotation_euler)
		# copy.scale *= obj.scale
		copy.matrix_parent_inverse 

	copy.name = name_original
	copies.append(copy)
	copy.location -= pivot
	return copy

def collect_objects_from_layer_collection(layer_collection):
	collection = layer_collection.collection
	for obj in collection.objects:
		if obj.parent is None:
			obj.select_set(True)

	for inner_layer_collection in layer_collection.children:
		if inner_layer_collection.exclude:
			continue
		collect_objects_from_layer_collection(inner_layer_collection)

def export(self, target_platform, exportAll):

	# Warnings
	if bpy.context.scene.FBXBundleSettings.path == "":
		self.report({'ERROR_INVALID_INPUT'}, "Export path not set" )
		return

	folder = os.path.dirname( bpy.path.abspath( bpy.context.scene.FBXBundleSettings.path ))
	if not os.path.exists(folder):
		self.report({'ERROR_INVALID_INPUT'}, "Path doesn't exist" )
		return

	if not exportAll and (len(bpy.context.selected_objects) == 0 and not bpy.context.view_layer.objects.active):
		self.report({'ERROR_INVALID_INPUT'}, "No objects selected" )
		return

	# Is Mode available?
	mode = bpy.context.scene.FBXBundleSettings.target_platform
	if mode not in platforms.platforms:
		self.report({'ERROR_INVALID_INPUT'}, "Platform '{}' not supported".format(mode) )
		return

	# Does the platform throw errors?
	if not platforms.platforms[mode].is_valid()[0]:
		self.report({'ERROR_INVALID_INPUT'}, platforms.platforms[mode].is_valid()[1] )
		return			


	# Store previous settings
	previous_selection = bpy.context.selected_objects.copy()
	previous_active = bpy.context.view_layer.objects.active
	previous_unit_system = bpy.context.scene.unit_settings.system
	previous_pivot = bpy.context.tool_settings.transform_pivot_point
	previous_cursor = bpy.context.scene.cursor.location.copy()

	# exporting all objects
	if exportAll:
		bpy.ops.object.select_all(action='DESELECT')
		bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection
		collect_objects_from_layer_collection(bpy.context.layer_collection)

	if not bpy.context.view_layer.objects.active:
		bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]

	bpy.ops.object.mode_set(mode='OBJECT')
	bundles = objects_organise.get_bundles()

	bpy.context.scene.unit_settings.system = 'METRIC'	
	bpy.context.tool_settings.transform_pivot_point = 'MEDIAN_POINT'

	objects_organise.recent_store(bundles)

	for name,objects in bundles.items():
		pivot = objects_organise.get_pivot(objects).copy()

		# Detect if animation export...
		use_animation = objects_organise.get_objects_animation(objects)

		copies = []
		originals = []
		for obj in objects:
			export_object(obj, prefix_copy, originals, copies, pivot)

		bpy.ops.object.select_all(action="DESELECT")
		for obj in copies:
			obj.select_set(state = True)
		bpy.context.view_layer.objects.active = copies[0]

		# Apply modifiers

		# full = self.process_path(name, path)+"{}".format(os.path.sep)+platforms.platforms[mode].get_filename( self.process_name(name) )  		
		 # os.path.join(folder, name)+"."+platforms.platforms[mode].extension
		path_folder = folder
		path_name = name
		for modifier in modifiers.modifiers:
			if modifier.get("active"):
				copies = modifier.process_objects(name, copies)
				path_folder = modifier.process_path(path_name, path_folder)
				path_name = modifier.process_name(path_name)

		path_full = os.path.join(path_folder, path_name)+"."+platforms.platforms[mode].extension
		
		# Create path if not yet available
		directory = os.path.dirname(path_full)
		pathlib.Path(directory).mkdir(parents=True, exist_ok=True)

		# Select all copies
		bpy.ops.object.select_all(action="DESELECT")
		for obj in copies:
			obj.select_set(state = True)

		# Export per platform (Unreal, Unity, ...)
		print("Export {}x = {}".format(len(objects),path_full))
		platforms.platforms[mode].file_export(path_full)

		# Delete copies
		bpy.ops.object.delete()
		copies.clear()
		
		# Restore names
		for obj in originals:
			obj.name = obj.name.replace(prefix_copy,"")

	# Restore previous settings
	bpy.context.scene.unit_settings.system = previous_unit_system
	bpy.context.tool_settings.transform_pivot_point = previous_pivot
	bpy.context.scene.cursor.location = previous_cursor
	bpy.context.view_layer.objects.active = previous_active
	bpy.ops.object.select_all(action='DESELECT')
	for obj in previous_selection:
		obj.select_set(state = True)

	# Show popup
	
	def draw(self, context):
		filenames = []
		# Get bundle file names
		for name,objects in bundles.items():
			for modifier in modifiers.modifiers:
				if modifier.get("active"):
					name = modifier.process_name(name)	
			filenames.append(name+"."+platforms.platforms[mode].extension)

		self.layout.label(text="Exported {}".format(", ".join(filenames)))

	bpy.context.window_manager.popup_menu(draw, title = "Exported {}x files".format(len(bundles)), icon = 'INFO')
	