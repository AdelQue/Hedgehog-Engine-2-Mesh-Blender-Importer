bl_info = {
    "name": "Hedgehog Engine 2 Import",
    "author": "Turk",
    "version": (1, 0, 0),
    "blender": (2, 82, 0),
    "location": "File > Import-Export",
    "description": "A script to import meshes from Hedgehog Engine 2 games",
    "warning": "",
    "category": "Import-Export",
}
import sys
import bpy
import bmesh
import os
import io
import struct
import math
import mathutils
from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )
from bpy_extras.io_utils import ImportHelper

class HedgeEngineTest(bpy.types.Operator, ImportHelper):
    bl_idname = "custom_import_scene.hedgeeng"
    bl_label = "Import"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".model"
    filter_glob: StringProperty(
            default="*.model;*.terrain-model",
            options={'HIDDEN'},
            )
    filepath: StringProperty(subtype='FILE_PATH',)
    files: CollectionProperty(type=bpy.types.PropertyGroup)
    
    import_strips: BoolProperty(
            name="Use Strips",
            description="Import mesh using strip notation",
            default=False,
            )
    use_yx_orientation: BoolProperty(
            name="Use YX Bone Orientation",
            description="Reorient bones from XZ to YX to make bones coincide with limbs and enable mirror support",
            default=False,
            )
    get_bone_lengths: BoolProperty(
            name="Use Bone Lengths",
            description="Calculate and apply approximate bone lengths",
            default=False,
            )
    
    def update_min_length(self, context):
        if self.get_bone_lengths_min > self.get_bone_lengths_max:
            self.get_bone_lengths_min = self.get_bone_lengths_max
    def update_max_length(self, context):
        if self.get_bone_lengths_min > self.get_bone_lengths_max:
            self.get_bone_lengths_max = self.get_bone_lengths_min
            
    get_bone_lengths_min: FloatProperty(
            name="Minimum Length",
            description="Calculated bone length will not exceed any lower than this value",
            default=0.025,
            min=0.01,
            soft_max=1.0,
            update=update_max_length,
            )
    get_bone_lengths_max: FloatProperty(
            name="Maximum Length",
            description="Calculated bone length will not exceed any higher than this value",
            default=0.600,
            min=0.01,
            soft_max=1.0,
            update=update_min_length,
            )
    get_bone_lengths_end: EnumProperty(
            items=[
                ("prevLength", "Parent Length", "Set end bone lengths to be the same as their respective parents", 1),
                ("minLength", "Minimum length", "Set end bone lengths to the minimum", 2),
                ("customLength", "Custom length", "Set end bone lengths to specified value", 3),
                ],
            name="End Bone Length",
            description="Determines how the end bones' lengths will be determined",
            default="prevLength",
            )
    get_bone_lengths_custom: FloatProperty(
            name="End Bone Length",
            description="End bone length",
            default=0.100,
            min=0.01,
            soft_max=1.0,
            )
    aligned_scale: BoolProperty(
            name="Aligned Scale Inheritance",
            description="Set bone scale inheritance mode to \"Aligned,\" which is the scale mode used in Frontiers",
            default=False,
            )
    
    def draw(self, context):
        layout = self.layout
        uiMeshBox = layout.box()
        uiMeshBox.label(text="Mesh Settings",icon="MESH_DATA")
        uiMeshBox.prop(self, "import_strips",)
        
        
        uiBoneBox = layout.box()
        uiBoneBox.label(text="Armature Settings",icon="ARMATURE_DATA")
        uiBoneBox.prop(self, "use_yx_orientation")
        uiBoneBox.prop(self, "get_bone_lengths")
    
        uiLengthBox = uiBoneBox.box()
        uiLengthRow = uiLengthBox.row()
        uiLengthRow.prop(self, "get_bone_lengths_min")
        uiLengthRow.prop(self, "get_bone_lengths_max")
        uiLengthBox.prop(self, "get_bone_lengths_end")
        if self.get_bone_lengths_end == "customLength":
            uiLengthBox.prop(self, "get_bone_lengths_custom")
        uiLengthBox.enabled = self.get_bone_lengths
        uiBoneBox.prop(self, "aligned_scale")


    def execute(self, context):
        dirname = os.path.dirname(self.filepath)
        for f in self.files:
            filepath = os.path.join(dirname, f.name)
            self.SkelPath = os.path.splitext(filepath)[0]+".skl.pxd"

            CurFile = open(filepath,"rb")
            CurCollection = bpy.data.collections.new(f.name) # Make Collection per lmd loaded
            bpy.context.scene.collection.children.link(CurCollection)

            CurFile.seek(0x8)
            tmpPointer = int.from_bytes(CurFile.read(4),byteorder='big')
            CurFile.seek(tmpPointer)
            tmpPointer = int.from_bytes(CurFile.read(4),byteorder='big')
            CurFile.seek(tmpPointer+0xC)
            MeshJump1Count = int.from_bytes(CurFile.read(4),byteorder='big')
            MeshJump1 = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
            CurFile.seek(0x8,1)
            BoneCount = int.from_bytes(CurFile.read(4),byteorder='big')
            BoneNameOffset = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
            BonePosOffset = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
            
            ObjArm = parse_skeleton(self,CurCollection)
            self.BoneRef = []
            
            for MJ1 in range(MeshJump1Count):
                CurFile.seek(MeshJump1+4*MJ1)
                CurFile.seek(int.from_bytes(CurFile.read(4),byteorder='big')+0x10)#reads pointer to mesh count
                MeshCount = int.from_bytes(CurFile.read(4),byteorder='big')
                if MeshCount == 0:
                    MeshCount = 1
                MeshTableOffset = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
                MaterialCount = int.from_bytes(CurFile.read(4),byteorder='big')
                MaterialTableOffset = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
                
                if os.path.exists(self.SkelPath):
                    parse_boneref_names(self,CurFile,BoneCount,BoneNameOffset)
                
                if BoneCount <=255:
                    self.BoneRefSize = 1
                else:
                    self.BoneRefSize = 2
                for mc in range(MeshCount):
                    CurFile.seek(MeshTableOffset+4*mc)
                    MeshHeader = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
                    parse_mesh(self,CurFile,MeshHeader,CurCollection,ObjArm)

            CurFile.close()
            del CurFile

        return {'FINISHED'}

def parse_mesh(self,CurFile,MeshHeader,CurCollection,ObjArm):
    CurFile.seek(MeshHeader)
    MaterialNamePointer = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
    IndiceCount = int.from_bytes(CurFile.read(4),byteorder='big')
    IndiceOffset = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
    VertCount = int.from_bytes(CurFile.read(4),byteorder='big')
    VertSize = int.from_bytes(CurFile.read(4),byteorder='big')
    VertChunkOffset = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
    VertDataTypeOffset = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
    BoneRefCount = int.from_bytes(CurFile.read(4),byteorder='big')
    BoneRefOffset = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
    
    CurFile.seek(MaterialNamePointer)
    MaterialName = readZeroTermString(CurFile)
    MeshMat = bpy.data.materials.get(MaterialName)
    if not MeshMat:
        MeshMat = bpy.data.materials.new(MaterialName)
    
    CurFile.seek(BoneRefOffset)
    BoneRefTable = []
    for x in range(BoneRefCount):
        BoneRefTable.append(int.from_bytes(CurFile.read(self.BoneRefSize),byteorder='big',signed=False))
    #print(BoneRefTable)
    
    CurFile.seek(IndiceOffset)
    FaceTable = []
    if self.import_strips:
        StripList = []
        tmpList = []
        for f in range(IndiceCount): 
            Indice = int.from_bytes(CurFile.read(2),byteorder='big')
            if Indice == 65535:
                StripList.append(tmpList.copy())
                tmpList.clear()
            else:
                tmpList.append(Indice)
                if f == IndiceCount-1:
                    StripList.append(tmpList.copy())
                    tmpList.clear()
        for f in StripList:
            for f2 in strip2face(f):
                FaceTable.append(f2)

    else:
        for x in range(0,IndiceCount,3):
            TempFace = struct.unpack('>HHH', CurFile.read(6))
            FaceTable.append((TempFace[2],TempFace[1],TempFace[0]))
    
    VertData = {}
    CurFile.seek(VertDataTypeOffset)
    VTypeOffset = 0
    while VTypeOffset < 0xff:
        VTypeOffset = int.from_bytes(CurFile.read(4),byteorder='big')
        VTypeFormat = int.from_bytes(CurFile.read(4),byteorder='big',signed=True)
        VTypeIndex = int.from_bytes(CurFile.read(4),byteorder='big',signed=False)
        if VTypeFormat == -1:
            break
        VertData[VTypeIndex] = [VTypeOffset,VTypeFormat]
    #print(VertData)
    
    VertPosOffset = VertData.get(0,[0])
    UVOffset = VertData.get(0x50000,[0])
    UV2Offset = VertData.get(0x50100,[0])
    UV3Offset = VertData.get(0x50200,[0])
    UV4Offset = VertData.get(0x50300,[0])
    NormalsOffset = VertData.get(0x30000,[0])
    ColorOffset = VertData.get(0xA0000)
    WBoneTable = VertData.get(0x20000)
    WBoneTable2 = VertData.get(0x20100)
    WWeightTable = VertData.get(0x10000)
    WWeightTable2 = VertData.get(0x10100)
    if WBoneTable:
        WBCount = 4
        if WBoneTable[1] == 0x1A225A:
            WBSize = 2
        else:
            WBSize = 1
    elif WBoneTable and WBoneTable2:
        WBCount = 8
    

    #CurFile.seek(VertChunkOffset)
    VertTable = []
    UVTable = []
    UV2Table = []
    UV3Table = []
    UV4Table = []
    NormalTable = []
    ColorTable = []
    WeightTable = []
    for x in range(VertCount):
        CurFile.seek(VertChunkOffset+x*VertSize+VertPosOffset[0])
        VertTable.append(struct.unpack('>fff', CurFile.read(4*3)))
        if UVOffset:
            CurFile.seek(VertChunkOffset+x*VertSize+UVOffset[0])
            TempUV = struct.unpack('>ee', CurFile.read(2*2))
            UVTable.append((TempUV[0],1-TempUV[1]))
        if UV2Offset:
            CurFile.seek(VertChunkOffset+x*VertSize+UV2Offset[0])
            TempUV = struct.unpack('>ee', CurFile.read(2*2))
            UV2Table.append((TempUV[0],1-TempUV[1]))
        if UV3Offset:
            CurFile.seek(VertChunkOffset+x*VertSize+UV3Offset[0])
            TempUV = struct.unpack('>ee', CurFile.read(2*2))
            UV3Table.append((TempUV[0],1-TempUV[1]))
        if UV4Offset:
            CurFile.seek(VertChunkOffset+x*VertSize+UV4Offset[0])
            TempUV = struct.unpack('>ee', CurFile.read(2*2))
            UV4Table.append((TempUV[0],1-TempUV[1]))
        CurFile.seek(VertChunkOffset+x*VertSize+NormalsOffset[0])
        if NormalsOffset[1] == 0x2A23B9:
            TempNorm = mathutils.Vector(struct.unpack('>fff', CurFile.read(4*3))).normalized()
        elif NormalsOffset[1] == 0x2A2187:
            TempNorm = mathutils.Vector(ten_bit_normal_read(int.from_bytes(CurFile.read(4),byteorder='big',signed=False))).normalized()
        #TempNorm = struct.unpack('>III', CurFile.read(12))
        #TempNorm = mathutils.Vector(((TempNorm[0]-0x7FFFFFFF)/0x7FFFFFFF,(TempNorm[1]-0x7FFFFFFF)/0x7FFFFFFF,(TempNorm[2]-0x7FFFFFFF)/0x7FFFFFFF)).normalized()
        NormalTable.append(TempNorm)
        if ColorOffset:
            CurFile.seek(VertChunkOffset+x*VertSize+ColorOffset[0])
            TempColor = struct.unpack('BBBB', CurFile.read(4))
            ColorTable.append((TempColor[3]/255,TempColor[2]/255,TempColor[1]/255,TempColor[0]/255))
        if WBoneTable:
            CurFile.seek(VertChunkOffset+x*VertSize+WBoneTable[0])
            tmpBone = []
            for w in range(WBCount):
                tmpBone.append(int.from_bytes(CurFile.read(WBSize),byteorder='big',signed=False))
            CurFile.seek(VertChunkOffset+x*VertSize+WWeightTable[0])
            tmpWeight = []
            for w in range(WBCount):
                tmpWeight.append(int.from_bytes(CurFile.read(1),byteorder='big',signed=False)/255)
            WeightTable.append((x,tmpBone,tmpWeight))
            
        
    #buildMesh
    mesh1 = bpy.data.meshes.new("Mesh")
    mesh1.use_auto_smooth = True
    obj = bpy.data.objects.new(MaterialName,mesh1)
    CurCollection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    mesh = bpy.context.object.data
    bm = bmesh.new()
    for v in VertTable:
        bm.verts.new((v[0],v[1],v[2]))
    list = [v for v in bm.verts]
    for f in FaceTable:
        try:
            bm.faces.new((list[f[0]],list[f[1]],list[f[2]]))
        except:
            continue             
    bm.to_mesh(mesh)

    if UVOffset:
        uv_layer = bm.loops.layers.uv.verify() # gets UVMap
    if UV2Offset:
        uv2_layer = bm.loops.layers.uv.new('UVMap2')
    if UV3Offset:
        uv3_layer = bm.loops.layers.uv.new('UVMap3')
    if UV4Offset:
        uv4_layer = bm.loops.layers.uv.new('UVMap4')

    Normals = []
    for f in bm.faces:
        f.smooth=True
        for l in f.loops:
            if NormalTable != []:
                Normals.append(NormalTable[l.vert.index])
            if UVOffset:
                l[uv_layer].uv  = UVTable[l.vert.index]  
            if UV2Offset:
                l[uv2_layer].uv = UV2Table[l.vert.index] 
            if UV3Offset:
                l[uv3_layer].uv = UV3Table[l.vert.index] 
            if UV4Offset:
                l[uv4_layer].uv = UV4Table[l.vert.index] 
    bm.to_mesh(mesh)

    if ColorOffset:
        color_layer = bm.loops.layers.color.new("Color")
        for f in bm.faces:
            for l in f.loops:
                l[color_layer]= ColorTable[l.vert.index]
        bm.to_mesh(mesh)

    bm.free()
    
    if len(obj.data.materials)>0:
        obj.data.materials[0]=MeshMat
    else:
        obj.data.materials.append(MeshMat)
    
    if WBoneTable and ObjArm:
        for i in WeightTable:
            for v in range(len(i[1])):
                if i[2][v] != 0:
                    if obj.vertex_groups.find(self.BoneRef[BoneRefTable[i[1][v]]]) == -1:
                        TempVG = obj.vertex_groups.new(name = self.BoneRef[BoneRefTable[i[1][v]]])
                    else:
                        TempVG = obj.vertex_groups[obj.vertex_groups.find(self.BoneRef[BoneRefTable[i[1][v]]])]
                    #print(i[2][v])
                    TempVG.add([i[0]],i[2][v],'ADD')
    
    if NormalTable != []:
        mesh1.normals_split_custom_set(Normals)
     
    if ObjArm:     
        ArmMod = obj.modifiers.new("Armature","ARMATURE")
        ArmMod.object = ObjArm
        obj.parent = ObjArm
        ObjArm.rotation_euler = (1.5707963705062866,0,0)
    else:
        obj.rotation_euler = (1.5707963705062866,0,0)

def parse_skeleton(self,CurCollection):
    if os.path.exists(self.SkelPath):
        print("Skel path found!\n")
        SkelFile = open(self.SkelPath,"rb")
        
        SkelFile.seek(0x48)
        SkelParentingOffset = int.from_bytes(SkelFile.read(4),byteorder='little')+0x40
        SkelFile.seek(4,1)
        SkelParentingCount = int.from_bytes(SkelFile.read(4),byteorder='little')
        SkelFile.seek(0x68)
        SkelNameTable = int.from_bytes(SkelFile.read(4),byteorder='little')+0x40
        SkelFile.seek(0x88)
        SkelPosOffset = int.from_bytes(SkelFile.read(4),byteorder='little')+0x40
        
        armature_data = bpy.data.armatures.new("Armature")
        armature_obj = bpy.data.objects.new("Armature", armature_data)
        CurCollection.objects.link(armature_obj)
        bpy.context.view_layer.objects.active = armature_obj
        utils_set_mode('EDIT')
        
        SkelTable = []
        for x in range(SkelParentingCount):
            SkelFile.seek(SkelParentingOffset+x*0x2)
            BoneParent = int.from_bytes(SkelFile.read(2),byteorder='little',signed=True)
            SkelFile.seek(SkelNameTable+x*0x10)
            SkelNameOffset = int.from_bytes(SkelFile.read(4),byteorder='little')+0x40
            SkelFile.seek(SkelNameOffset)
            BoneName = readZeroTermString(SkelFile)
            SkelFile.seek(SkelPosOffset+x*0x30)
            TmpVec = struct.unpack('<fff', SkelFile.read(4*3))
            if self.use_yx_orientation:
                BoneVec = (TmpVec[2],TmpVec[0],TmpVec[1])
            else:
                BoneVec = (TmpVec[0],TmpVec[1],TmpVec[2])
            SkelFile.seek(4,1)
            TempRot = struct.unpack('<ffff', SkelFile.read(4*4))
            if self.use_yx_orientation:
                BoneRot = (TempRot[3],TempRot[2],TempRot[0],TempRot[1])
            else:
                BoneRot = (TempRot[3],TempRot[0],TempRot[1],TempRot[2])
                
            SkelTable.append({"Pos":BoneVec,"Rot":BoneRot})
            
            edit_bone = armature_obj.data.edit_bones.new(BoneName)
            edit_bone.use_connect = False
            edit_bone.use_inherit_rotation = True
            edit_bone.use_inherit_scale = True
            if self.aligned_scale:
                edit_bone.inherit_scale = 'ALIGNED'
            edit_bone.use_local_location = True
            edit_bone.head = (0,0,0)
            if self.use_yx_orientation:
                edit_bone.tail = (0.1,0,0)
                edit_bone.roll = -1.5707963705062866
            else:
                edit_bone.tail = (0,0.1,0)
            if BoneParent > -1:
                edit_bone.parent = armature_obj.data.edit_bones[BoneParent]
        utils_set_mode('POSE')
        for x in range(SkelParentingCount):
            pbone = armature_obj.pose.bones[x]
            pbone.rotation_mode = 'QUATERNION'
            pbone.rotation_quaternion = SkelTable[x]["Rot"]
            pbone.location = SkelTable[x]["Pos"]
        bpy.ops.pose.armature_apply()
        
        if self.get_bone_lengths: 
            utils_set_mode('EDIT')
            for x in range(SkelParentingCount):
                edit_bone = armature_obj.data.edit_bones[x]
                child_bone = None
                
                for child_bone_test in edit_bone.children: # Find child with the most children as the bone to calculate length from
                    test = 0
                    count = len(child_bone_test.children_recursive)
                    if child_bone_test == edit_bone.children[0] or test < count:
                        test = count
                        child_bone = child_bone_test
                
                if child_bone:
                    Len = (edit_bone.head - child_bone.head).length
                elif self.get_bone_lengths_end == "prevLength":
                    Len = edit_bone.parent.length
                elif self.get_bone_lengths_end == "customLength":
                    Len = self.get_bone_lengths_custom
                else:
                    Len = self.get_bone_lengths_min
                
                if Len > self.get_bone_lengths_max:
                    edit_bone.length = self.get_bone_lengths_max
                elif Len < self.get_bone_lengths_min:
                    edit_bone.length = self.get_bone_lengths_min
                else:
                    edit_bone.length = Len
                
        utils_set_mode('OBJECT')
        
        SkelFile.close()
        del SkelFile
        return armature_obj
    else:
        return False
  
def parse_boneref_names(self,CurFile,BoneCount,BoneNameOffset):
    for x in range(BoneCount):
        CurFile.seek(BoneNameOffset+x*4)
        tmpPointer = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
        CurFile.seek(tmpPointer+4)
        tmpPointer = int.from_bytes(CurFile.read(4),byteorder='big')+0x10
        CurFile.seek(tmpPointer)
        BoneRefName = readZeroTermString(CurFile)
        self.BoneRef.append(BoneRefName)
    return
  
def sign_ten_bit(Input):
    if Input < 0x200: return Input
    else: return Input - 0x400
    end
    
def readZeroTermString(CurFile):
    TempBytes = []
    while True:
        b = CurFile.read(1)
        if b is None or b[0] == 0:
            return bytes(TempBytes).decode('utf-8')
        else:
            TempBytes.append(b[0])
    
def strip2face(strip):
    flipped = False
    tmpTable = []
    for x in range(len(strip)-2):
        if flipped:
            tmpTable.append((strip[x+1],strip[x+2],strip[x]))
        else:
            tmpTable.append((strip[x+2],strip[x+1],strip[x]))
        flipped = not flipped
    return tmpTable
    
def ten_bit_normal_read(RawNorm):
    Norm1 = sign_ten_bit(RawNorm & 0x3ff)/512
    Norm2 = sign_ten_bit((RawNorm >> 10) & 0x3ff)/512
    Norm3 = sign_ten_bit((RawNorm >> 20) & 0x3ff)/512
    return (Norm1,Norm2,Norm3)

def utils_set_mode(mode):
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode=mode, toggle=False)

def menu_func_import(self, context):
    self.layout.operator(HedgeEngineTest.bl_idname, text="Hedgehog Engine (.model)")
        
def register():
    bpy.utils.register_class(HedgeEngineTest)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    
def unregister():
    bpy.utils.unregister_class(HedgeEngineTest)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
        
if __name__ == "__main__":
    register()
