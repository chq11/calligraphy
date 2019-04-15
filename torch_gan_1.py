import torch
import torch.nn as nn
from torch.nn import init
from torch.utils.data import DataLoader,Dataset
from torch.autograd import Variable
import torchvision
import torchvision.transforms as T
import torch.optim as optim
from torch.utils.data import DataLoader
from torch.utils.data import sampler
import torchvision.datasets as dset
import numpy as np
from units import *
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import os
os.environ["CUDA_VISIBLE_DEVICES"] = '9'

#matplotlib inline
plt.rcParams['figure.figsize'] = (10.0, 8.0) # set default size of plots
plt.rcParams['image.interpolation'] = 'nearest'
plt.rcParams['image.cmap'] = 'gray'

def show_images(images):
    images = np.reshape(images, [images.shape[0], -1])  # images reshape to (batch_size, D)
    sqrtn = int(np.ceil(np.sqrt(images.shape[0])))
    sqrtimg = int(np.ceil(np.sqrt(images.shape[1])))

    fig = plt.figure(figsize=(sqrtn, sqrtn))
    gs = gridspec.GridSpec(sqrtn, sqrtn)
    gs.update(wspace=0.05, hspace=0.05)

    for i, img in enumerate(images):
        ax = plt.subplot(gs[i])
        plt.axis('off')
        ax.set_xticklabels([])
        ax.set_yticklabels([])
        ax.set_aspect('equal')
        plt.imshow(img.reshape([sqrtimg,sqrtimg]))
    return

def preprocess_img(x):
    return 2 * x - 1.0

def deprocess_img(x):
    return (x + 1.0) / 2.0

def rel_error(x,y):
    return np.max(np.abs(x - y) / (np.maximum(1e-8, np.abs(x) + np.abs(y))))

def count_params(model):
    """Count the number of parameters in the current TensorFlow graph """
    param_count = np.sum([np.prod(p.size()) for p in model.parameters()])
    return param_count

answers = np.load('gan-checks-tf.npz')

# 采样函数为自己定义的序列采样（即按顺序采样）
class ChunkSampler(sampler.Sampler):
    """Samples elements sequentially from some offset.
    Arguments:
        num_samples: # of desired datapoints
        start: offset where we should start selecting from
    """
    def __init__(self, num_samples, start=0):
        self.num_samples = num_samples
        self.start = start

    def __iter__(self):
        return iter(range(self.start, self.start + self.num_samples))

    def __len__(self):
        return self.num_samples

NUM_TRAIN = 50000   # 训练集数量
NUM_VAL = 5000      # 测试集数量
NOISE_DIM = 1024
Batch_size = 512
Show_every = 1
Num_epochs = 50000

img_width = 128
img_height = 128
random_scale = False
hsv = True
augment = False
preprocess = False
List_path = './list/calligraphy/'
train_list = List_path+'all_train_list.txt'
# mnist_train = dset.MNIST('./cs231n/datasets/MNIST_data', train=True, download=True,
#                            transform=T.ToTensor())
# print(mnist_train[0])
# loader_train = DataLoader(mnist_train, batch_size=Batch_size,
#                           sampler=ChunkSampler(NUM_TRAIN, 0)) # 从0位置开始采样NUM_TRAIN个数
#
# mnist_val = dset.MNIST('./cs231n/datasets/MNIST_data', train=True, download=True,
#                            transform=T.ToTensor())
# loader_val = DataLoader(mnist_val, batch_size=batch_size,
#                         sampler=ChunkSampler(NUM_VAL, NUM_TRAIN)) # 从NUM_TRAIN位置开始采样NUM_VAL个数

class GANNetworkDataset(Dataset):
    def __init__(self, train_list):
        self.imageFolderDataset = open(train_list, 'r')
        self.lines = self.imageFolderDataset.readlines()
        self.imageFolderDataset.close()

    def __getitem__(self, index):
        line = self.lines[index].strip().split(' ')
        label = int(line[-1])
        img_path = line[0]

        img = load_img(img_path, target_size=(img_width, img_height))
        img = img_to_array(img)
        if random_scale:
            scale_ratio = random.uniform(0.9, 1.1)
        #img = padding_byRatio(img_path, return_width=img_width)
        if hsv:
            # Change from RGB space to HSV space
            img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            # Mapping to [0, 255]
            img = np.interp(img, [img.min(), img.max()], [0, 1])

        if augment:
            img = np.reshape(img.astype(np.uint8))
            img = seq.augment_images(img)

        if preprocess:
            img = preprocessing_eye(img, return_image=True,
                                            result_size=(img_width, img_height))

        return img[:,:,2], torch.from_numpy(np.array(label, dtype=np.float32))

    def __len__(self):
        return len(self.lines)

calligraphy_dataset = GANNetworkDataset(train_list=train_list)
# print(np.shape(calligraphy_dataset[2][0]))
loader_train = DataLoader(calligraphy_dataset, shuffle=False, num_workers=8, batch_size=Batch_size)

imgs = loader_train.__iter__().next()[0].numpy().squeeze()
# print(imgs.shape)
show_images(imgs)

def sample_noise(batch_size, dim):
    """
    Generate a PyTorch Tensor of uniform random noise.

    Input:
    - batch_size: Integer giving the batch size of noise to generate.
    - dim: Integer giving the dimension of noise to generate.

    Output:
    - A PyTorch Tensor of shape (batch_size, dim) containing uniform
      random noise in the range (-1, 1).
    """
    temp = torch.rand(batch_size, dim) + torch.rand(batch_size, dim)*(-1)

    return temp

class Flatten(nn.Module):
    def forward(self, x):
        N, C, H, W = x.size() # read in N, C, H, W
        return x.view(N, -1)  # "flatten" the C * H * W values into a single vector per image

class Unflatten(nn.Module):
    """
    An Unflatten module receives an input of shape (N, C*H*W) and reshapes it
    to produce an output of shape (N, C, H, W).
    """
    def __init__(self, N=-1, C=128, H=7, W=7):
        super(Unflatten, self).__init__()
        self.N = N
        self.C = C
        self.H = H
        self.W = W
    def forward(self, x):
        return x.view(self.N, self.C, self.H, self.W)

def initialize_weights(m):
    if isinstance(m, nn.Linear) or isinstance(m, nn.ConvTranspose2d):
        nn.init.xavier_uniform_(m.weight.data)

# dtype = torch.FloatTensor
dtype = torch.cuda.FloatTensor ## UNCOMMENT THIS LINE IF YOU'RE ON A GPU!
def discriminator():
    """
    Build and return a PyTorch model implementing the architecture above.
    """
    model = nn.Sequential(
        Flatten(),
        nn.Linear(784,256),
        nn.LeakyReLU(0.01, inplace=True),
        nn.Linear(256,256),
        nn.LeakyReLU(0.01, inplace=True),
        nn.Linear(256,1)
    )
    return model

def generator(noise_dim=NOISE_DIM):
    """
    Build and return a PyTorch model implementing the architecture above.
    """
    model = nn.Sequential(
        nn.Linear(noise_dim, 1024),
        nn.ReLU(inplace=True),
        nn.Linear(1024, 1024),
        nn.ReLU(inplace=True),
        nn.Linear(1024, 784),#784
        nn.Tanh(),
    )
    return model


#----------------------------------------------------------------------------------------------------
def build_dc_classifier():
    """
    Build and return a PyTorch model for the DCGAN discriminator implementing
    the architecture above.
    """
    # return nn.Sequential(
    #     Unflatten(Batch_size, 1, 28, 28),
    #     nn.Conv2d(1, 32, kernel_size=5, stride=1),
    #     nn.LeakyReLU(negative_slope=0.01),
    #     nn.MaxPool2d(2, stride=2),
    #     nn.Conv2d(32, 64, kernel_size=5, stride=1),
    #     nn.LeakyReLU(negative_slope=0.01),
    #     nn.MaxPool2d(kernel_size=2, stride=2),
    #     Flatten(),
    #     nn.Linear(4 * 4 * 64, 4 * 4 * 64),
    #     nn.LeakyReLU(negative_slope=0.01),
    #     nn.Linear(4 * 4 * 64, 1)
    # )

    return nn.Sequential(
        Unflatten(Batch_size, 1, 128, 128),           #28,28,32        #128,128,16
        nn.Conv2d(1, 16,kernel_size=5, stride=1),   #24,24,32          #124,124,16
        nn.LeakyReLU(negative_slope=0.01),
        nn.MaxPool2d(2, stride=2),                  #12,12,32          #62,62,16
        nn.Conv2d(16, 32,kernel_size=5, stride=1),  # 8, 8,64          #58,58,32
        nn.LeakyReLU(negative_slope=0.01),
        nn.MaxPool2d(kernel_size=2, stride=2),      # 4, 4,64          #29,29,32
        nn.Conv2d(32, 64, kernel_size=5, stride=1),                    #25,25,64
        nn.LeakyReLU(negative_slope=0.01),
        nn.MaxPool2d(kernel_size=2, stride=2),                         #12,12,64
        nn.Conv2d(64, 128, kernel_size=5, stride=1),                   # 8, 8,128
        nn.LeakyReLU(negative_slope=0.01),
        nn.MaxPool2d(kernel_size=2, stride=2),                         # 4, 4,128
        Flatten(),
        nn.Linear(4*4*128, 4*4*128),                  # 4*4*64          # 4*4*128
        nn.LeakyReLU(negative_slope=0.01),
        nn.Linear(4*4*128,1)                         # 4*4*64           # 4*4*128
    )

data = Variable(loader_train.__iter__().next()[0]).type(dtype)
# print(np.shape(data.cpu().numpy()))
b = build_dc_classifier().type(dtype)
out = b(data)
print(out.size())

def build_dc_generator(noise_dim=NOISE_DIM):
    """
    Build and return a PyTorch model implementing the DCGAN generator using
    the architecture described above.
    """
    # return nn.Sequential(
    #     nn.Linear(noise_dim, 1024),
    #     nn.ReLU(),
    #     nn.BatchNorm1d(1024),
    #     nn.Linear(1024, 7 * 7 * 128),
    #     nn.BatchNorm1d(7 * 7 * 128),
    #     Unflatten(Batch_size, 128, 7, 7),
    #     nn.ConvTranspose2d(in_channels=128, out_channels=64, kernel_size=4, stride=2, padding=1),
    #     nn.ReLU(inplace=True),
    #     nn.BatchNorm2d(num_features=64),
    #     nn.ConvTranspose2d(in_channels=64, out_channels=1, kernel_size=4, stride=2, padding=1),
    #     nn.Tanh(),
    #     Flatten(),
    # )

    model = nn.Sequential(
        nn.Linear(noise_dim, 1024),
        nn.ReLU(),
        nn.BatchNorm1d(1024),
        nn.Linear(1024, 8*8*128),
        nn.BatchNorm1d(8*8*128),
        Unflatten(Batch_size, 128, 8, 8),
        nn.ConvTranspose2d(in_channels=128, out_channels=64, kernel_size=4, stride=2, padding=1),
        nn.ReLU(inplace=True),
        nn.BatchNorm2d(num_features=64),
        nn.ConvTranspose2d(in_channels=64, out_channels=32, kernel_size=4, stride=2, padding=1),
        nn.ReLU(inplace=True),
        nn.BatchNorm2d(num_features=32),
        nn.ConvTranspose2d(in_channels=32, out_channels=16, kernel_size=4, stride=2, padding=1),
        nn.ReLU(inplace=True),
        nn.BatchNorm2d(num_features=16),
        nn.ConvTranspose2d(in_channels=16, out_channels=1, kernel_size=4, stride=2, padding=1),
        nn.Tanh(),
        Flatten(),
    )
    return model

test_g_gan = build_dc_generator().type(dtype)
test_g_gan.apply(initialize_weights)

fake_seed = Variable(torch.randn(Batch_size, NOISE_DIM)).type(dtype)
# print(np.shape(fake_seed.cpu().numpy()))
fake_images = test_g_gan.forward(fake_seed)
print(fake_images.size())

#----------------------------------------------------------------------------------------------------
Bce_loss = nn.BCEWithLogitsLoss()

def discriminator_loss(logits_real, logits_fake):
    """
    Computes the discriminator loss described above.

    Inputs:
    - logits_real: PyTorch Variable of shape (N,) giving scores for the real data.
    - logits_fake: PyTorch Variable of shape (N,) giving scores for the fake data.

    Returns:
    - loss: PyTorch Variable containing (scalar) the loss for the discriminator.
    """
    #loss = None
    # Batch size.
    N = logits_real.size()

    # 目标label，全部设置为1意味着判别器需要做到的是将正确的全识别为正确，错误的全识别为错误
    true_labels = Variable(torch.ones(N)).type(dtype)


    real_image_loss = Bce_loss(logits_real, true_labels) # 识别正确的为正确
    fake_image_loss = Bce_loss(logits_fake, 1 - true_labels) # 识别错误的为错误

    loss = real_image_loss + fake_image_loss

    return loss

def generator_loss(logits_fake):
    """
    Computes the generator loss described above.

    Inputs:
    - logits_fake: PyTorch Variable of shape (N,) giving scores for the fake data.

    Returns:
    - loss: PyTorch Variable containing the (scalar) loss for the generator.
    """
    # Batch size.
    N = logits_fake.size()

    # 生成器的作用是将所有“假”的向真的（1）靠拢
    true_labels = Variable(torch.ones(N)).type(dtype)

    # 计算生成器损失
    loss = Bce_loss(logits_fake, true_labels)

    return loss

def ls_discriminator_loss(scores_real, scores_fake):
    """
    Compute the Least-Squares GAN loss for the discriminator.

    Inputs:
    - scores_real: PyTorch Variable of shape (N,) giving scores for the real data.
    - scores_fake: PyTorch Variable of shape (N,) giving scores for the fake data.

    Outputs:
    - loss: A PyTorch Variable containing the loss.
    """
    N = scores_real.size()
#     print(N)

    true_labels = Variable(torch.ones(N)).type(dtype)

    fake_image_loss = (torch.mean((scores_real - true_labels)**2))
    real_image_loss = (torch.mean((scores_fake)**2))

    loss = 0.5*fake_image_loss + 0.5*real_image_loss

    return loss

def ls_generator_loss(scores_fake):
    """
    Computes the Least-Squares GAN loss for the generator.

    Inputs:
    - scores_fake: PyTorch Variable of shape (N,) giving scores for the fake data.

    Outputs:
    - loss: A PyTorch Variable containing the loss.
    """
    N = scores_fake.size()

    true_labels = Variable(torch.ones(N)).type(dtype)

    loss = 0.5 * ((torch.mean((scores_fake - true_labels)**2)))

    return loss

def get_optimizer(model):
    """
    Construct and return an Adam optimizer for the model with learning rate 1e-3,
    beta1=0.5, and beta2=0.999.

    Input:
    - model: A PyTorch model that we want to optimize.

    Returns:
    - An Adam optimizer for the model with the desired hyperparameters.
    """
    optimizer = optim.Adam(model.parameters(), lr=0.001, betas=(0.5, 0.999))
    return optimizer

def run_a_gan(D, G, D_solver, G_solver, discriminator_loss, generator_loss, show_every=250,
              batch_size=128, noise_size=96, num_epochs=10):
    """
    Train a GAN!

    Inputs:
    - D, G: pytorch模块，分别为判别器和生成器
    - D_solver, G_solver: torch.optim Optimizers to use for training the
      discriminator and generator.
    - discriminator_loss, generator_loss: Functions to use for computing the generator and
      discriminator loss, respectively.
    - show_every: Show samples after every show_every iterations.
    - batch_size: Batch size to use for training.
    - noise_size: Dimension of the noise to use as input to the generator.
    - num_epochs: Number of epochs over the training dataset to use for training.
    """
    for epoch in range(num_epochs):
        for x, _ in loader_train:
            if len(x) != batch_size:
                continue
            D_solver.zero_grad()
            real_data = Variable(x).type(dtype)
            logits_real = D(2 * (real_data - 0.5)).type(dtype)

            g_fake_seed = Variable(sample_noise(batch_size, noise_size)).type(dtype)
            fake_images = G(g_fake_seed).detach()
            logits_fake = D(fake_images.view(batch_size, 1, img_width, img_height))

            d_total_error = discriminator_loss(logits_real, logits_fake)
            d_total_error.backward()
            D_solver.step()

            G_solver.zero_grad()
            g_fake_seed = Variable(sample_noise(batch_size, noise_size)).type(dtype)
            fake_images = G(g_fake_seed)

            gen_logits_fake = D(fake_images.view(batch_size, 1, img_width, img_height))
            g_error = generator_loss(gen_logits_fake)
            g_error.backward()
            G_solver.step()

        if (epoch % show_every == 0):
            print('Epoch : {}, D: {:.4}, G:{:.4}'.format(epoch, d_total_error.item(), g_error.item()))
            imgs_numpy = fake_images.data.cpu().numpy()
            show_images(imgs_numpy[0:16])
            plt.show()

# Make the discriminator
# D = discriminator().type(dtype)
#
# # Make the generator
# G = generator().type(dtype)
#
# # Use the function you wrote earlier to get optimizers for the Discriminator and the Generator
# D_solver = get_optimizer(D)
# G_solver = get_optimizer(G)
# # Run it!
# # run_a_gan(D, G, D_solver, G_solver, discriminator_loss, generator_loss)
# run_a_gan(D, G, D_solver, G_solver, ls_discriminator_loss, ls_generator_loss)
#
D_DC = build_dc_classifier().type(dtype)
D_DC.apply(initialize_weights)
G_DC = build_dc_generator().type(dtype)
G_DC.apply(initialize_weights)
#
D_DC_solver = get_optimizer(D_DC)
G_DC_solver = get_optimizer(G_DC)

run_a_gan(D_DC, G_DC, D_DC_solver, G_DC_solver, ls_discriminator_loss, generator_loss,batch_size=Batch_size,
          show_every=Show_every, noise_size=NOISE_DIM, num_epochs=Num_epochs)
