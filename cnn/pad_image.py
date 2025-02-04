import os
import numpy as np
import cv2
import tifffile as tifffile
from tqdm import tqdm
import pandas as pd
import argparse  # Add argparse to handle user arguments

def pad_image_to_64x64(img, output_path):
    # Get the size of the image
    if img.shape[0] == 3:
        height, width = img.shape[1:]
    else:
        height, width = img.shape
    if height == 0 or width == 0:
        return
    elif img is None:
        return
    # Calculate padding
    top = (64 - height) // 2
    bottom = 64 - height - top
    left = (64 - width) // 2
    right = 64 - width - left

    if top < 0:
        top = 0
    if bottom < 0:
        bottom = 0
    if right < 0:
        right = 0
    if left < 0:
        left = 0
    # Pad the image with zeros (black)
    if img.shape[0] == 3:
        padded_img_R = cv2.copyMakeBorder(img[0,:,:], top, bottom, left, right, cv2.BORDER_CONSTANT, value=[0, 0, 0])
        padded_img_G = cv2.copyMakeBorder(img[1,:,:], top, bottom, left, right, cv2.BORDER_CONSTANT, value=[0, 0, 0])
        padded_img_B = cv2.copyMakeBorder(img[2,:,:], top, bottom, left, right, cv2.BORDER_CONSTANT, value=[0, 0, 0])
        padded_img = np.stack([padded_img_R,padded_img_G,padded_img_B])
    else:
        padded_img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=[0, 0, 0])
    tifffile.imwrite(output_path, padded_img,photometric='minisblack')

def get_max_cell(list_of_cells):
    df = pd.DataFrame()
    df['FoF'] = [i['FoF'] for i in list_of_cells]
    df['cell_shape'] = [i['image_shape'] for i in list_of_cells]
    df_max = df.groupby(['FoF']).max()
    df_max2 = df_max.reset_index()
    return df_max2

def get_cell_data(path2Patches,path2SaveDir):
    print('Getting cell shape maximum...')
    list_of_data = []
    for CellCycle in os.listdir(path2Patches):
        if CellCycle.startswith('._') or not os.path.isdir(os.path.join(path2Patches, CellCycle)):
            continue # skip temp folders  and files
        if not os.path.exists(os.path.join(path2SaveDir,CellCycle,'images_padded')):
            os.makedirs(os.path.join(path2SaveDir,CellCycle,'images_padded')) # create a folder to save padded images
        for imageName in tqdm(os.listdir(os.path.join(path2Patches, CellCycle,'images'))):
            if imageName.startswith('._') or not imageName.endswith('.tif'):
                continue
            path2Image = os.path.join(path2Patches, CellCycle,'images',imageName)
            #path2Save = os.path.join(path2Patches,CellCycle,'images_padded',imageName)
            path2Save = os.path.join(path2SaveDir,CellCycle,'images_padded',imageName)
            image = tifffile.imread(path2Image)
            image_shape = image.shape
            FoF = imageName.split('_slice')[0]
            data_dict = {'path2Image': path2Image,'path2Save':path2Save,'image_shape':image_shape,'FoF':FoF}
            list_of_data.append(data_dict)
    df_max_cell = get_max_cell(list_of_data)
    return list_of_data, df_max_cell

def pad_data(list_of_data, df_max_cell):
    print('Padding the images, please wait...')
    for item in tqdm(list_of_data):
        percentage_reduction_x = 0
        percentage_reduction_y = 0
        path2Image = item['path2Image']
        path2Save = item['path2Save']
        image_shape = item['image_shape']
        FoF = item['FoF']
        max_shape = df_max_cell.loc[df_max_cell['FoF'] == FoF, 'cell_shape'].values
        if len(max_shape[0]) > 2:
            if max_shape[0][1] > 64:
                percentage_reduction_x = 64 / float(max_shape[0][1])
            if max_shape[0][2] > 64:
                percentage_reduction_y = 64 / float(max_shape[0][2])
        elif len(max_shape[0]) == 2:
            if max_shape[0][0] > 64:
                percentage_reduction_x = 64 / float(max_shape[0][0])
            if max_shape[0][1] > 64:
                percentage_reduction_y = 64 / float(max_shape[0][1])

        image = tifffile.imread(path2Image)
        try:
            if percentage_reduction_x == 0 and percentage_reduction_y == 0:
                image_resized = image
                pass
            else:
                if len(image.shape) > 2:
                    new_x = image.shape[1] * percentage_reduction_x
                    new_y = image.shape[2] * percentage_reduction_y
                    image_resized1 = cv2.resize(image[0,:,:],dsize=(int(new_y),int(new_x)),interpolation=cv2.INTER_AREA)
                    image_resized2 = cv2.resize(image[1,:,:],dsize=(int(new_y),int(new_x)),interpolation=cv2.INTER_AREA)
                    image_resized3 = cv2.resize(image[2,:,:],dsize=(int(new_y),int(new_x)),interpolation=cv2.INTER_AREA)
                    image_resized = np.stack([image_resized1,image_resized2,image_resized3])
                elif len(image.shape) == 2:
                    new_x = image.shape[0] * percentage_reduction_x
                    new_y = image.shape[1] * percentage_reduction_y  
                    image_resized = cv2.resize(image,dsize=(int(new_y),int(new_x)),interpolation=cv2.INTER_AREA)
        except Exception as e:
            print('Error {}'.format(e))
        pad_image_to_64x64(image_resized, path2Save)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pad image patches to 64x64 for training.')
    parser.add_argument('path2Patches', type=str, help='Path to the patches directory.')
    parser.add_argument('path2Save',type=str,help='Path to directory for saving the patches')
    args = parser.parse_args()
    list_of_data, df_max_cell = get_cell_data(args.path2Patches,args.path2Save)
    pad_data(list_of_data, df_max_cell)
