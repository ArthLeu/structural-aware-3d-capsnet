"""beta_vae_train.py"""

import argparse
import sys
import os

import torch
import torch.nn.parallel
from torch.autograd import Variable
import torch.optim as optim

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(BASE_DIR, '../../')))
sys.path.append(os.path.abspath(os.path.join(BASE_DIR, '../../dataloaders')))

import shapenet_part_loader
import shapenet_core13_loader
import shapenet_core55_loader
from model import PointCapsNet
from solver import kl_divergence, reconstruction_loss
from logger import Logger

USE_CUDA = True
LOGGING = True


def main():
    USE_CUDA = True
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    #capsule_net = BetaPointCapsNet(opt.prim_caps_size, opt.prim_vec_size, opt.latent_caps_size, opt.latent_vec_size, opt.num_points)
    capsule_net = PointCapsNet(opt.prim_caps_size, opt.prim_vec_size, opt.latent_caps_size, opt.latent_vec_size, opt.num_points)
  
    if opt.model != '':
        capsule_net.load_state_dict(torch.load(opt.model))
 
    if USE_CUDA:       
        print("Let's use", torch.cuda.device_count(), "GPUs!")
        capsule_net = torch.nn.DataParallel(capsule_net)
        capsule_net.to(device)

    # create folder to save trained models
    if not os.path.exists(opt.outf):
        os.makedirs(opt.outf)

    # create folder to save logs
    if LOGGING:
        log_dir='./logs'+'/'+opt.dataset+'_dataset_'+str(opt.latent_caps_size)+'caps_'+str(opt.latent_vec_size)+'vec'+'_batch_size_'+str(opt.batch_size)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        logger = Logger(log_dir)

    # select dataset    
    if opt.dataset=='shapenet_part':
        train_dataset = shapenet_part_loader.PartDataset(classification=True, npoints=opt.num_points, split='train')
        train_dataloader = torch.utils.data.DataLoader(train_dataset, batch_size=opt.batch_size, shuffle=True, num_workers=4)        
    elif opt.dataset=='shapenet_core13':
        train_dataset = shapenet_core13_loader.ShapeNet(normal=False, npoints=opt.num_points, train=True)
        train_dataloader = torch.utils.data.DataLoader(train_dataset, batch_size=opt.batch_size, shuffle=True, num_workers=4)
    elif opt.dataset=='shapenet_core55':
        train_dataset = shapenet_core55_loader.Shapnet55Dataset(batch_size=opt.batch_size, npoints=opt.num_points, shuffle=True, train=True)

    # BVAE CONFIGURATIONS HARDCODING
    #loss_mode = 'gaussian' # loss_mode was decoder_list in bVAE
    loss_mode = 'chamfer' 

    global_iter = 0


    # training process for 'shapenet_part' or 'shapenet_core13'
    #capsule_net.train()
    if 'train_dataloader' in locals().keys() :
        for epoch in range(opt.n_epochs+1):
            if epoch < 50:
                optimizer = optim.Adam(capsule_net.parameters(), lr=0.01)
            elif epoch<150:
                optimizer = optim.Adam(capsule_net.parameters(), lr=0.001)
            else:
                optimizer = optim.Adam(capsule_net.parameters(), lr=0.0001)

            capsule_net.train()
            train_loss_sum, recon_loss_sum, beta_loss_sum = 0, 0, 0

            for batch_id, data in enumerate(train_dataloader):
                global_iter += 1

                points, _= data
                if(points.size(0)<opt.batch_size):
                    break
                points = Variable(points)
                points = points.transpose(2, 1)
                if USE_CUDA:
                    points = points.cuda()
    
                optimizer.zero_grad()
                
                # ---- CRITICAL PART: new train loss computation (train_loss in bVAE was beta_vae_loss)
                #x_recon, latent_caps, caps_recon, logvar = capsule_net(points) # returns x_recon, latent_caps, caps_recon, logvar
                latent_capsules, x_recon = capsule_net(points)
                recon_loss = reconstruction_loss(points, x_recon, "chamfer") # RECONSTRUCTION LOSS
                train_loss = recon_loss

                # combining per capsule loss (pyTorch requires)
                train_loss.backward()
                optimizer.step()
                train_loss_sum += train_loss.item()

                # ---- END OF CRITICAL PART ----
                
                if LOGGING:
                    info = {'train loss': train_loss.item()}
                    for tag, value in info.items():
                        logger.scalar_summary(
                            tag, value, (len(train_dataloader) * epoch) + batch_id + 1)                
              
                if batch_id % 50 == 0:
                    print('batch_no: %d / %d, train_loss: %f ' %  (batch_id, len(train_dataloader), train_loss.item()))
    
            print('\nAverage train loss of epoch %d : %f\n' %\
                (epoch, (train_loss_sum / len(train_dataloader))))

            if epoch% 5 == 0:
                dict_name = "%s/%s_dataset_%dcaps_%dvec_%d.pth"%\
                    (opt.outf, opt.dataset, opt.latent_caps_size, opt.latent_vec_size, epoch)
                torch.save(capsule_net.module.state_dict(), dict_name)

    # training process for 'shapenet_core55' (NOT UP-TO-DATE)
    else:
        raise NotImplementedError()

if __name__ == "__main__":

    print("[INFO] tmp_checkpoints folder will be in your program run folder")
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch_size', type=int, default=8, help='input batch size')
    parser.add_argument('--n_epochs', type=int, default=50, help='number of epochs to train for')

    parser.add_argument('--prim_caps_size', type=int, default=1024, help='number of primary point caps')
    parser.add_argument('--prim_vec_size', type=int, default=16, help='scale of primary point caps')
    parser.add_argument('--latent_caps_size', type=int, default=64, help='number of latent caps')
    parser.add_argument('--latent_vec_size', type=int, default=64, help='scale of latent caps')

    parser.add_argument('--num_points', type=int, default=2048, help='input point set size')
    parser.add_argument('--outf', type=str, default='tmp_checkpoints', help='output folder')
    parser.add_argument('--model', type=str, default='', help='model path')
    parser.add_argument('--dataset', type=str, default='shapenet_part', help='dataset')
    

    opt = parser.parse_args()
    print("Args:", opt)

    main()
