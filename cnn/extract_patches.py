import os
import sys
import pandas as pd
import cv2
import numpy as np
import tifffile as tifffile
from tqdm import tqdm
from glob import glob
import argparse  # Importing argparse for command-line arguments



import os
import sys 
import pandas as pd 
import cv2 
import numpy as np
import tifffile as tifffile
from tqdm import tqdm
from glob import glob
#path2FoF = '/Users/saeedalahmari/Documents/AWS/BioInformaticsPaper/NCI-N87/A05_Cellpose_SegmentationCorrected'

def normalize8(I):
  mn = I.min()
  mx = I.max()

  mx -= mn

  I = ((I - mn)/mx) * 255
  return I.astype(np.uint8)

#extract_patchs_3ch(data_dict,slice_mask,cell_id,cell_Cycle)
def extract_patchs_3ch(data_dict,slice_mask,cell_id,cell_Cycle,z,path2Save,FoF):
    # Find unique pixels using numpy
    unique_values = np.unique(slice_mask)
    #print(unique_values)
    nucleus_tif = data_dict['nucleus']
    image_masked = np.zeros_like(slice_mask)
    if 'cyto' in data_dict and 'mito' in data_dict:
        cyto_tif = data_dict['cyto']
        mito_tif = data_dict['mito']
        image_masked[0,:,:] = slice_mask[0,:,:].astype(nucleus_tif.dtype) * nucleus_tif[z,:,:]
        image_masked[1,:,:] = slice_mask[1,:,:].astype(nucleus_tif.dtype) * cyto_tif[z,:,:]
        image_masked[2,:,:] = slice_mask[2,:,:].astype(nucleus_tif.dtype) * mito_tif[z,:,:]
    else:
        if len(nucleus_tif.shape) == 4:
            nucleus_tif_temp = cv2.cvtColor(nucleus_tif[z,:,:],cv2.COLOR_BGR2GRAY)
            image_masked = slice_mask.astype(nucleus_tif.dtype) * nucleus_tif_temp 
            cyto_tif = nucleus_tif
            mito_tif = nucleus_tif
            image_masked = np.expand_dims(image_masked,0)
        else:
            image_masked = slice_mask.astype(nucleus_tif.dtype) * nucleus_tif[z,:,:] 
            cyto_tif = nucleus_tif
            mito_tif = nucleus_tif
            image_masked = np.expand_dims(image_masked,0)
    ################################
    cell_mask = (slice_mask > 0)* 255 
    mask_temp = np.zeros(cell_mask.shape, dtype=np.uint8)
    cell_mask = cell_mask.astype(np.uint8)

    if 'cyto' in data_dict and 'mito' in data_dict:
        contours_1, _ = cv2.findContours(cell_mask[0,:,:], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours_2, _ = cv2.findContours(cell_mask[0,:,:], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours_3, _ = cv2.findContours(cell_mask[0,:,:], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    else:
        contours_1, _ = cv2.findContours(cell_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for contour in contours_1:
        mask_temp = np.zeros(cell_mask.shape, dtype=np.uint8)
        # Create a mask for the current contour
        cv2.drawContours(mask_temp, [contour], -1, 255, thickness=cv2.FILLED)
        # Find bounding box of the contour
        x, y, w, h = cv2.boundingRect(contour)
        if w * h < 10: # skip small cells. 
            return 0
        elif abs(y - 10) < 1 or abs(x - 10) < 1:
            return 0
        elif (y + h + 10) >= image_masked.shape[1] or (x + w + 10) >= image_masked.shape[2]:
            return 0
        image_extracted_n = image_masked[0,y - 10:y + h + 10, x - 10:x + w + 10]
        image_extracted_n = image_extracted_n.astype(np.float32)

    if 'cyto' in data_dict and 'mito' in data_dict:
        for contour in contours_2:
            mask_temp = np.zeros(cell_mask.shape, dtype=np.uint8)
            # Create a mask for the current contour
            cv2.drawContours(mask_temp, [contour], -1, 255, thickness=cv2.FILLED)
            # Find bounding box of the contour
            x, y, w, h = cv2.boundingRect(contour)
            if w * h < 10: # skip small cells. 
                return 0
            elif abs(y - 10) < 1 or abs(x - 10) < 1:
                return 0
            elif (y + h + 10) >= image_masked.shape[1] or (x + w + 10) >= image_masked.shape[2]:
                return 0
            image_extracted_c = image_masked[1,y - 10:y + h + 10, x - 10:x + w + 10]
            image_extracted_c = image_extracted_c.astype(np.float32)
        for contour in contours_3:
            mask_temp = np.zeros(cell_mask.shape, dtype=np.uint8)
            # Create a mask for the current contour
            cv2.drawContours(mask_temp, [contour], -1, 255, thickness=cv2.FILLED)
            # Find bounding box of the contour
            x, y, w, h = cv2.boundingRect(contour)
            if w * h < 10: # skip small cells. 
                return 0
            elif abs(y - 10) < 1 or abs(x - 10) < 1:
                return 0
            elif (y + h + 10) >= image_masked.shape[1] or (x + w + 10) >= image_masked.shape[2]:
                return 0
            image_extracted_m = image_masked[2,y - 10:y + h + 10, x - 10:x + w + 10]
            image_extracted_m = image_extracted_m.astype(np.float32)
        image_extracted = np.stack([image_extracted_n, image_extracted_c,image_extracted_m])
    else:
        image_extracted = image_extracted_n

    if not os.path.exists(os.path.join(path2Save,'cellCycle'+str(cell_Cycle),'images')):
        os.makedirs(os.path.join(path2Save,'cellCycle'+str(cell_Cycle),'images'))
    tifffile.imwrite(os.path.join(path2Save,'cellCycle'+str(cell_Cycle),'images',FoF+'_slice'+str(z)+'_cellCycle'+str(cell_Cycle)+'_cell'+str(cell_id)+'.tif'),image_extracted)

def generate_mask(compartments_loc,path2Images,cell_id,FoF,cell_Cycle,path2Save):
    image_tif = tifffile.imread(os.path.join(path2Images,'nucleus.p.tif'))
    image_tif_shape = image_tif.shape
    Flag_mito = False
    Flag_cyto = False
    nucleus_cell_loc = pd.read_csv(compartments_loc["nucleus"])

    nucleus_mask = np.zeros((70,1024,1024))
    for x,y,z in zip(nucleus_cell_loc['x'],nucleus_cell_loc['y'],nucleus_cell_loc['z']):
        nucleus_mask[int(z-1),int(y-1),int(x-1)] = int(cell_id)

    if os.path.exists(os.path.join(path2Images,'mito.p.tif')) and compartments_loc["mito"] is not None:
        mito_tif = tifffile.imread(os.path.join(path2Images,'mito.p.tif'))
        Flag_mito = True
        mito_cell_loc = pd.read_csv(compartments_loc["mito"])

        mito_mask = np.zeros((70,1024,1024))
        for x,y,z in zip(mito_cell_loc['x'],mito_cell_loc['y'],mito_cell_loc['z']):
            mito_mask[int(z-1),int(y-1),int(x-1)] = int(cell_id)

    if os.path.exists(os.path.join(path2Images,'cytoplasm.p.tif')) and compartments_loc["cytoplasm"] is not None:
        cyto_tif = tifffile.imread(os.path.join(path2Images,'cytoplasm.p.tif'))
        Flag_cyto = True 
        cyto_cell_loc = pd.read_csv(compartments_loc["cytoplasm"])

        cyto_mask = np.zeros((70,1024,1024))
        for x,y,z in zip(cyto_cell_loc['x'],cyto_cell_loc['y'],cyto_cell_loc['z']):
            cyto_mask[int(z-1),int(y-1),int(x-1)] = int(cell_id)
    #print(image_tif_shape)

    for z in range(0,nucleus_mask.shape[0]):
        mask_n = nucleus_mask[z,:,:]
        data_dict = {'nucleus':image_tif}
        if not mask_n.max() > 0:
            continue
        if Flag_mito and Flag_cyto:
            mask_c = cyto_mask[z,:,:]
            mask_m = mito_mask[z,:,:]
            data_dict = {'nucleus':image_tif,'cyto':cyto_tif,'mito':mito_tif}
            slice_mask = np.stack([mask_n,mask_m,mask_c])
        else:
            data_dict = {'nucleus':image_tif}
            slice_mask = mask_n
        extract_patchs_3ch(data_dict,slice_mask,cell_id,cell_Cycle,z,path2Save,FoF)
def process_FoF(path2FoF, path2CellMasks, path2Save):
    # for FoF in os.listdir(path2FoF):
        # if not os.path.isdir(os.path.join(path2FoF,FoF)):
        #     continue 
        # label_file = glob(os.path.join(path2FoF,FoF,"assignedCompartments2Nucleus","*.txt"))
        csv_files = glob(os.path.join(path2CellMasks, "nucleus.p*.csv"))
        path2Images = os.path.join(path2FoF)
        for csv_path in csv_files:
            csv_file = os.path.basename(csv_path)
            print(csv_file)
            if csv_file.startswith('._*'):
                continue # skip temp file 
            cell_id = csv_file.split('cell_')[1].split('_')[0]
            nucleus_path = csv_path
            try:
                mito_path = csv_path.replace('nucleus.p','mito.p')
                cyto_path = csv_path.replace('nucleus.p','cytoplasm.p')
            except:
                mito_path = None
                cyto_path = None
            print('cell_id: {}'.format(cell_id))
            df = pd.read_csv(csv_path)
            # Ensure cellCycle column exists or set it to 0 if it doesn't
            if 'cellCycle' not in df.columns:
                df['cellCycle'] = 0
                print('No cell cycle label provided. Setting to zero.')
            print(df.shape)
            if df.shape[0] != 0:
                compartments_loc = {'nucleus':nucleus_path,'cytoplasm':cyto_path,'mito':mito_path}
                cell_Cycle = df['cellCycle'].iloc[0]
                print('cell_Cycle:'.format(cell_Cycle))
                generate_mask(compartments_loc,path2Images,cell_id,"FoF",cell_Cycle,path2Save)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Process Fields of View (FoF)")
    parser.add_argument('path2FoF', type=str, help="Path to the folder of interest (FoF)")
    parser.add_argument('path2CellMasks', type=str, help="Path to the Cell_Masks folder")
    parser.add_argument('path2Save', type=str, help="Path to save the output Cell_patches")
    args = parser.parse_args()
    path2FoF = args.path2FoF
    path2CellMasks = args.path2CellMasks
    path2Save = args.path2Save
    print(f"path2FoF: {path2FoF}")
    print(f"path2CellMasks: {path2CellMasks}")
    print(f"path2Save: {path2Save}")
    process_FoF(path2FoF, path2CellMasks, path2Save)
