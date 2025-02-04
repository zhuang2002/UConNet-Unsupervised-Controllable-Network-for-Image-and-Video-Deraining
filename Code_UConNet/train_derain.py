import torch
import numpy as np
from Network.model import *
import torchvision as tv
from lib.dataset import *
import argparse
from torch.utils.data import DataLoader
seed=1#424
torch.manual_seed(seed)
torch.cuda.manual_seed(seed)
torch.cuda.manual_seed_all(seed)
np.random.seed(seed)  # Numpy module.
random.seed(seed)  # Python random module.
parser = argparse.ArgumentParser(description="AngleNet")
parser.add_argument("--batchSize", type=int, default=16, help="Training batch size")
parser.add_argument("--epochs", type=int, default=5, help="Number of training epochs")
parser.add_argument("--milestone", type=list, default=[20, 60, 80], help="When to decay learning rate;")
parser.add_argument("--lr", type=float, default=1e-3, help="Initial learning rate")
parser.add_argument("--outf", type=str, default="output", help='path of log files')
parser.add_argument("--rain_path",type=str,default=r"",help='path of rain dataset')
parser.add_argument("--reset", type=int, default=1, help='path of dataset')
opt = parser.parse_args()


os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
from matplotlib import pyplot as plt
transform = tv.transforms.Compose(
    [#tv.transforms.Resize(128),
        tv.transforms.ToTensor()
        # tv.transforms.Normalize(mean=[0.5,0.5,0.5],std=[0.5,0.5,0.5])
    ])

def main():
    repeat = 2500
    device_ids = [0]
    dataset_train = rain_data(opt.rain_path, transforms=transform, patch_size=128, batch_size=opt.batchSize,
                               repeat=repeat, channel=3)
    loader_train = DataLoader(dataset=dataset_train, num_workers=8, batch_size=opt.batchSize, shuffle=True)
    derainNet = derain_Net().cuda()
    derainNet.apply(weights_init_kaiming)
    derain_optimizer = torch.optim.Adam(derainNet.parameters(), lr=opt.lr, eps=1e-4, amsgrad=True)
    derainNet = nn.DataParallel(derainNet, device_ids=device_ids).cuda()
    derain_schedulr = torch.optim.lr_scheduler.MultiStepLR(derain_optimizer, milestones=[20, 60, 80], gamma=0.2, last_epoch=-1)

    AngleNet = Angle_Net(in_channels=3).cuda()
    AngleNet = nn.DataParallel(AngleNet).cuda()
    AngleNet.load_state_dict(torch.load(r'.\result_model\AngleNet/Angle.pth'))
    AngleNet.eval()

    angle_loss = Angle_loss()
    for epoch in range(opt.epochs):
        mean_loss = 0
        for i, data in enumerate(loader_train):
            image = data['rain_data'].type(torch.FloatTensor).cuda()
            image_Y,Cb,Cr = yCbCr2rgb(image)
            image_Y = image_Y.unsqueeze(1)
            with torch.no_grad():
                angle_predicted = AngleNet(image)
                angle_predicted = (angle_predicted*120-60)/180*3.1415926535897
                angle_predicted = torch.reshape(angle_predicted,(angle_predicted.shape[0],1))
            a = torch.rand(3,opt.batchSize).cuda()
            a = a+0.4#0.4
            sum_a = torch.sum(a,dim= 0)
            a = a/sum_a
            a = a.detach()
            out = derainNet(image_Y.detach(),a.detach(),angle_predicted.detach(),True)
            kernel = get_kernel_conv(-angle_predicted).unsqueeze(1)
            kernel_T = get_kernel_conv_T(-angle_predicted).unsqueeze(1)
            a1 = a[0, :].unsqueeze(1).unsqueeze(1).unsqueeze(1)
            a2 = a[1, :].unsqueeze(1).unsqueeze(1).unsqueeze(1)*28
            a3 = a[2, :].unsqueeze(1).unsqueeze(1).unsqueeze(1)*16
            loss = L1_loss(image_Y.detach(),out,a1)+angle_loss(image_Y.detach()-out,kernel,a2)+angle_loss(out,kernel_T,a3)
            # print(loss)
            mean_loss+=loss
            derain_optimizer.zero_grad()
            loss.backward()
            derain_optimizer.step()
        print('The ' + str(epoch) + ' epoch：', mean_loss / 2500)
        if epoch % 1 == 0:
            torch.save(derainNet.state_dict(), r'.\result_model\UConNet/UconNet_epoch' + str(epoch) + '.pth')
            # test_net('Angle_net_withReal_'+str(epoch)+'.pth')
        derain_schedulr.step()


if __name__ == "__main__":
    main()